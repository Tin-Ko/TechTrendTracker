"""Build the project recommendations catalog.

Pipeline (all offline, all local):
    1. mine frequent skill triples from job_postings   (triple_miner)
    2. for each triple, generate a project via Gemma    (generator)
    3. upsert into project_recommendations              (this module)

The Go backend then serves projects with a pure `skills <@ $top5` lookup at
request time -- no model, no cloud LLM. Re-run this whenever the posting
corpus has grown enough to shift the popular skill combinations.

Usage:
    python -m data_pipeline.recommendations.build_catalog \\
        --min-support 25 --min-lift 1.0 --top-n 200
"""

from __future__ import annotations

import argparse
import os
import uuid

import psycopg

from data_pipeline.recommendations.generator import ProjectGenerator
from data_pipeline.recommendations.triple_miner import TripleStat, mine_triples


# uuid5 over the sorted-skills key => the same triple always maps to the same
# row across re-runs, so ON CONFLICT upserts in place instead of accumulating
# duplicates. Fixed namespace so the mapping is stable.
_NAMESPACE = uuid.UUID("6f8d2e4a-9c1b-4e7a-9b2f-1a3c5d7e9f01")

_UPSERT_SQL = """
INSERT INTO project_recommendations
    (project_id, title, level, blurb, skills,
     support_count, lift, score, skills_key, generated_at)
VALUES
    (%(project_id)s, %(title)s, %(level)s, %(blurb)s, %(skills)s,
     %(support_count)s, %(lift)s, %(score)s, %(skills_key)s, now())
ON CONFLICT (project_id) DO UPDATE SET
    title         = EXCLUDED.title,
    level         = EXCLUDED.level,
    blurb         = EXCLUDED.blurb,
    skills        = EXCLUDED.skills,
    support_count = EXCLUDED.support_count,
    lift          = EXCLUDED.lift,
    score         = EXCLUDED.score,
    generated_at  = EXCLUDED.generated_at
"""


def _skills_key(skills: tuple[str, str, str]) -> str:
    # The miner already returns sorted triples (s1 < s2 < s3); normalize
    # defensively so casing/order can never split one triple into two rows.
    return "|".join(sorted(s.lower() for s in skills))


def upsert_project(cur, triple: TripleStat, title: str, level: str, blurb: str) -> None:
    key = _skills_key(triple.skills)
    cur.execute(
        _UPSERT_SQL,
        {
            "project_id": str(uuid.uuid5(_NAMESPACE, key)),
            "title": title,
            "level": level,
            "blurb": blurb,
            "skills": list(triple.skills),
            "support_count": triple.support_count,
            "lift": triple.lift,
            # Request-time ranking signal: popularity of the combo. lift already
            # gated the catalog at build time, so support orders the surviving
            # projects "most buildable / most in-demand" first.
            "score": float(triple.support_count),
            "skills_key": key,
        },
    )


def build(*, min_support: int, min_lift: float, top_n: int, max_skills: int) -> None:
    dsn = os.environ.get("SUPABASE_DB_DIRECT_URL")
    if not dsn:
        raise SystemExit("SUPABASE_DB_URL not set (use the direct 5432 string for this batch job)")

    generator = ProjectGenerator()

    # autocommit + prepare_threshold=None mirror SupabaseClient: each upsert is
    # its own transaction, and prepared-statement names won't collide with the
    # Supavisor pooler.
    with psycopg.connect(dsn, autocommit=True, prepare_threshold=None) as conn:
        triples = mine_triples(
            conn,
            min_support=min_support,
            min_lift=min_lift,
            top_n=top_n,
            max_skills=max_skills,
        )
        print(
            f"Mined {len(triples)} triples "
            f"(min_support={min_support}, min_lift={min_lift}, top_n={top_n})"
        )

        ok = 0
        with conn.cursor() as cur:
            for i, t in enumerate(triples, 1):
                try:
                    project = generator.generate(t.skills)
                except Exception as e:  # noqa: BLE001 - skip a bad triple, keep the batch going
                    print(f"[{i}/{len(triples)}] skip {t.skills}: {e}")
                    continue
                upsert_project(cur, t, project.title, project.level, project.blurb)
                ok += 1
                print(
                    f"[{i}/{len(triples)}] {t.skills} "
                    f"(n={t.support_count}, lift={t.lift:.2f}) -> {project.title}"
                )

        print(f"Upserted {ok}/{len(triples)} projects into project_recommendations")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the project recommendations catalog.")
    ap.add_argument("--min-support", type=int, default=25,
                    help="min postings a triple must appear in (default 25)")
    ap.add_argument("--min-lift", type=float, default=1.0,
                    help="drop triples with lift below this; 1.0 = chance (default 1.0)")
    ap.add_argument("--top-n", type=int, default=200,
                    help="cap on how many triples to generate projects for (default 200)")
    ap.add_argument("--max-skills", type=int, default=30,
                    help="per-posting skill cap to bound the O(k^3) join (default 30)")
    args = ap.parse_args()
    build(
        min_support=args.min_support,
        min_lift=args.min_lift,
        top_n=args.top_n,
        max_skills=args.max_skills,
    )


if __name__ == "__main__":
    main()
