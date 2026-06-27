"""Offline frequent-triple mining over job_postings.skills.

A "project" in the recommendations catalog is built from a triple of skills
that co-occur in real postings. This module finds those triples: it counts how
many postings contain each unordered {A, B, C}, keeps the ones above a minimum
support, and scores their association strength with lift.

Read-only against job_postings; the Go request path never runs this.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import psycopg


@dataclass(frozen=True)
class TripleStat:
    skills: tuple[str, str, str]  # sorted so s1 < s2 < s3
    support_count: int            # postings containing all three
    lift: float                   # P(A,B,C) / (P(A)P(B)P(C)); > 1 = real affinity


# How the SQL works:
#   * `a < b < c` makes each unordered triple count once and kills permutation
#     duplicates -- without it every triple would appear 3! = 6 times.
#   * `skills[1:%(max_skills)s]` caps the per-posting array before the triple
#     cross join. The join is O(k^3) in a posting's skill count k, so one
#     pathological posting with dozens of skills would otherwise dominate.
#   * `array_agg(DISTINCT s)` guards against a skill repeated inside one posting
#     double-counting a triple.
#   * lift is computed inline from single-skill support (`singles`) and the
#     corpus size (`total`); the WHERE on the final select drops triples whose
#     lift is below the floor (weak/anti-correlated combos make bad projects).
_MINE_SQL = """
WITH postings AS (
    SELECT posting_id,
           (SELECT array_agg(DISTINCT s)
              FROM unnest(skills[1:%(max_skills)s]) AS s) AS skills
    FROM job_postings
    WHERE cardinality(skills) >= 3
),
total AS (
    SELECT COUNT(*)::numeric AS n FROM postings
),
singles AS (
    SELECT s AS skill, COUNT(*)::numeric AS cnt
    FROM postings, unnest(skills) AS s
    GROUP BY s
),
triples AS (
    SELECT a AS s1, b AS s2, c AS s3, COUNT(*)::int AS support_count
    FROM postings p
    CROSS JOIN LATERAL unnest(p.skills) AS a
    CROSS JOIN LATERAL unnest(p.skills) AS b
    CROSS JOIN LATERAL unnest(p.skills) AS c
    WHERE a < b AND b < c
    GROUP BY a, b, c
    HAVING COUNT(*) >= %(min_support)s
)
SELECT t.s1, t.s2, t.s3, t.support_count,
       ((t.support_count / n.n)
         / ((sa.cnt / n.n) * (sb.cnt / n.n) * (sc.cnt / n.n)))::float8 AS lift
FROM triples t
CROSS JOIN total n
JOIN singles sa ON sa.skill = t.s1
JOIN singles sb ON sb.skill = t.s2
JOIN singles sc ON sc.skill = t.s3
WHERE ((t.support_count / n.n)
        / ((sa.cnt / n.n) * (sb.cnt / n.n) * (sc.cnt / n.n))) >= %(min_lift)s
ORDER BY t.support_count DESC
LIMIT %(top_n)s
"""


def mine_triples(
    conn: psycopg.Connection,
    *,
    min_support: int = 25,
    min_lift: float = 1.0,
    top_n: int = 200,
    max_skills: int = 30,
) -> List[TripleStat]:
    """Return the top `top_n` frequent skill triples by support.

    min_support  -- a triple must appear in at least this many postings.
    min_lift     -- drop triples whose lift is below this (1.0 = no better than
                    chance). Filters out "three popular skills that happen to
                    collide" in favour of combos with a genuine affinity.
    max_skills   -- per-posting skill cap that bounds the O(k^3) cross join.
    """
    with conn.cursor() as cur:
        cur.execute(
            _MINE_SQL,
            {
                "min_support": min_support,
                "min_lift": min_lift,
                "top_n": top_n,
                "max_skills": max_skills,
            },
        )
        rows = cur.fetchall()

    return [
        TripleStat(skills=(s1, s2, s3), support_count=cnt, lift=float(lift))
        for (s1, s2, s3, cnt, lift) in rows
    ]
