from __future__ import annotations
import functools, json, logging, os, time, unicodedata
from dataclasses import dataclass
from typing import Optional
import ollama
from data_pipeline.llm_processor import facet_parser
import re

log = logging.getLogger(__name__)



LLM_MODEL = os.environ.get("LLM_MODEL", "gemma4:latest")

class TitleLLMError(Exception):
    """Raised when the model returns unparseable or invalid output after one retry."""

@dataclass(frozen=True) # Frozen so it is hashable, hence safe as an lru cache value
class TitleDecision:
    canonical_title: str
    role_family: Optional[str]
    specializations: tuple[str, ...] # tuples are hashable, lists are not

    @classmethod
    def abstain(cls, key: str) -> "TitleDecision":
        # If the LLM can't make the decision, return the key as canonical title
        return cls(canonical_title=key, role_family=None, specializations=())

    @classmethod
    def from_db(cls, row: tuple) -> "TitleDecision":
        canonical, role_family, specs = row
        return cls(canonical, role_family, tuple(specs or ()))

    def to_db(self) -> tuple:
        return (self.canonical_title, self.role_family, list(self.specializations))

    @property
    def is_placed(self) -> bool:
        return self.role_family is not None




def normalize_title_key(raw: str) -> str:
    """Normalizes a raw job title string into a consistent key."""
    
    # 1. Unicode normalize and lowercase
    processed_title = unicodedata.normalize('NFKC', raw).lower()
    
    # 2. Delete bracketed segments: (...) and [...]
    processed_title = re.sub(r'[\(\[][^\)\]]*[\)\]]', ' ', processed_title)
    
    # 3. Truncate at the first '|'
    if '|' in processed_title:
        processed_title = processed_title.split('|', 1)[0]

    # 4. Remove seniority tokens (using source of truth from facet_parser)
    for _, pattern in facet_parser._SENIORITY_PATTERNS:
        processed_title = pattern.sub('', processed_title)
            
    # 5. Remove year tokens (using source of truth from facet_parser)
    processed_title = facet_parser._YEAR_RE.sub('', processed_title)
    
    # 6. Remove leftover punctuation except '&' '+' '/' '-'
    # Keep letters, numbers, space, &, +, /, -
    processed_title = re.sub(r'[^a-z0-9 &+/#-]', ' ', processed_title) # Clear disallowed punctuation
    processed_title = re.sub(r'(^| )-+( |$)', ' ', processed_title)     # Drop dangling hyphen
    processed_title = re.sub(r'\s+', ' ', processed_title).strip()      # Collapse + trim

    return processed_title


# ─────────────────────────────────────────────────────────────────────────────
# Constants (design §6.2 / §6.3)
# ─────────────────────────────────────────────────────────────────────────────

PROMPT_PATH = os.path.join("constants", "title_norm_prompt.txt")
PROMPT_VERSION = "title-norm-v1"   # bump on ANY edit to the prompt file (§6.2)
REGISTRY_TTL_SECS = 600            # family/spec lists cached in-process ~10 min
MAX_SPECS = 4                      # sanity caps from validate_decision (§6.2)
MAX_CANONICAL_WORDS = 6

# Deterministic head-noun rewrites applied in validate_decision so
# "backend developer" and "backend engineer" converge on ONE canonical row.
# v1 policy (Appendix B note): apply unconditionally; revisit if it grates.
HEAD_NOUN_MAP = {
    "developer": "engineer",
    "programmer": "engineer",
    "swe": "engineer",
}


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers (design §6.2)
#
# Every function below takes a live psycopg connection — from the ingest
# worker that is `SupabaseClient().conn`. That connection is autocommit=True,
# so each execute() commits itself; you never need conn.commit() here.
# ─────────────────────────────────────────────────────────────────────────────


def load_family_registry(conn) -> list[str]:
    """Known role families, most-populated first. Design §6.2."""
    # TODO 1. What to do:
    #    Query the role_families table and return the family names as a
    #    plain list of strings, ordered by posting_count DESC. The ordering
    #    matters: this list is interpolated into the LLM prompt, and prompt
    #    attention is position-biased, so frequent families must come first.
    #
    # TODO 2. Recommended approach:
    #    A single SELECT:
    #        SELECT family FROM role_families ORDER BY posting_count DESC;
    #    Open a cursor with `with conn.cursor() as cur:`, execute, fetchall,
    #    and pull the first column out of each row tuple.
    #
    # TODO 3. Implementation details:
    #    - Do NOT cache here. Caching (with the TTL) lives in TitleNormalizer
    #      so there is exactly one place where staleness can happen.
    #    - An empty list on a fresh DB is fine — the prompt template must
    #      tolerate it (the LLM will just propose families, which is intended
    #      bootstrap behavior). Don't raise on empty.
    with conn.cursor() as cur:
        cur.execute("SELECT family FROM role_families ORDER BY posting_count DESC;")
        return [row[0] for row in cur.fetchall()]
        




def load_spec_vocab(conn) -> list[str]:
    """Active specialization vocabulary for the prompt. Design §6.2."""
    # TODO 1. What to do:
    #    Return every spec from spec_vocabulary whose status = 'active'.
    #    'pending' and 'rejected' specs are deliberately excluded — pending
    #    ones haven't been reviewed yet and must not be reinforced by
    #    appearing in the prompt.
    #
    # TODO 2. Recommended approach:
    #    SELECT spec FROM spec_vocabulary WHERE status = 'active' ORDER BY spec;
    #    (Alphabetical order is fine here — unlike families there's no
    #    frequency signal to exploit, and a stable order keeps prompts
    #    reproducible across runs, which helps when debugging LLM output.)
    #
    # TODO 3. Implementation details:
    #    - Same shape as load_family_registry: cursor, execute, list of col 0.
    #    - Keep the two loaders as separate functions even though they look
    #      similar — they diverge later (e.g. if you add per-family specs).
    with conn.cursor() as cur:
        cur.execute("SELECT spec FROM spec_vocabulary WHERE status = 'activ' ORDER by spec;")
        return [row[0] for row in cur.fetchall()]


def lookup_title_map(conn, key: str) -> Optional[TitleDecision]:
    """Memo-table lookup: has this normalized title been decided before?"""
    # TODO 1. What to do:
    #    Fetch the single title_map row whose primary key equals `key` and
    #    return it as a TitleDecision, or None when no row exists. This is
    #    the L2 cache in the ladder (L1 is the in-process dict).
    #
    # TODO 2. Recommended approach:
    #    SELECT canonical_title, role_family, specializations
    #    FROM title_map WHERE raw_title_norm = %s;
    #    then `row = cur.fetchone()`; if row is None return None, otherwise
    #    return TitleDecision.from_db(row) — you already wrote that helper,
    #    and its column order matches this SELECT on purpose. Keep it that way.
    #
    # TODO 3. Implementation details:
    #    - Select the three columns explicitly (never SELECT *) so a future
    #      schema change can't silently shift what from_db receives.
    #    - psycopg returns Postgres TEXT[] as a Python list; from_db already
    #      converts it to a tuple, so no extra handling needed here.
    raise NotImplementedError


def register_new_family(conn, family: str) -> None:
    """Insert an LLM-proposed family into the registry. Design §6.2."""
    # TODO 1. What to do:
    #    Insert `family` into role_families if it isn't already there.
    #    Called from validate_decision when the LLM proposes a family that
    #    isn't in the current registry (allowed — the weekly reconcile job
    #    reviews small families, §8).
    #
    # TODO 2. Recommended approach:
    #    INSERT INTO role_families (family) VALUES (%s) ON CONFLICT DO NOTHING;
    #
    # TODO 3. Implementation details:
    #    - ON CONFLICT DO NOTHING makes this safe to call concurrently and
    #      repeatedly — two workers proposing the same family is not an error.
    #    - posting_count stays at its DEFAULT 0; only reconcile maintains it.
    raise NotImplementedError


def register_new_spec(conn, spec: str, status: str = "pending") -> None:
    """Insert an LLM-proposed spec into the vocabulary. Design §6.2."""
    # TODO 1. What to do:
    #    Same as register_new_family but for spec_vocabulary, defaulting the
    #    status to 'pending' (LLM-proposed specs are quarantined until the
    #    reconcile job promotes/merges/rejects them).
    #
    # TODO 2. Recommended approach:
    #    INSERT INTO spec_vocabulary (spec, status) VALUES (%s, %s)
    #    ON CONFLICT DO NOTHING;
    #
    # TODO 3. Implementation details:
    #    - ON CONFLICT DO NOTHING also means: if the spec already exists as
    #      'rejected', this call will NOT resurrect it. That is the behavior
    #      we want — rejection is a human decision and sticks.
    raise NotImplementedError


def upsert_title_map(
    conn,
    key: str,
    decision: TitleDecision,
    source: str,
    model_version: Optional[str],
    prompt_version: Optional[str],
) -> None:
    """Memoize a decision. First writer wins — by design. §6.2."""
    # TODO 1. What to do:
    #    Insert one row into title_map recording the decision plus its
    #    provenance (source, model_version, prompt_version). If a row for
    #    this key already exists, do NOTHING — do not overwrite. Rewriting
    #    existing decisions is exclusively the reconcile job's power; this
    #    prevents a model upgrade from silently churning the whole taxonomy.
    #
    # TODO 2. Recommended approach:
    #    INSERT INTO title_map (raw_title_norm, canonical_title, role_family,
    #                           specializations, source, model_version,
    #                           prompt_version)
    #    VALUES (%s, %s, %s, %s, %s, %s, %s)
    #    ON CONFLICT (raw_title_norm) DO NOTHING;
    #    Use decision.to_db() for the three decision columns — note it already
    #    converts the specs tuple back to a list, which psycopg adapts to
    #    TEXT[] natively.
    #
    # TODO 3. Implementation details:
    #    - `source` is one of: ingest_llm | backfill | query_llm | manual |
    #      merge (schema comment). The callers pass it in; don't default it.
    #    - decided_at has a DEFAULT now() — leave it out of the column list.
    raise NotImplementedError


# ─────────────────────────────────────────────────────────────────────────────
# LLM path (design §6.2 / §6.3)
# ─────────────────────────────────────────────────────────────────────────────


def build_normalizer_prompt(
    key: str, families: list[str], specs: list[str]
) -> tuple[str, str]:
    """Assemble (system_prompt, user_msg) for one cache-miss title. §6.2."""
    # TODO 1. What to do:
    #    Load the system-prompt template from constants/title_norm_prompt.txt
    #    (skeleton already created — finish its few-shot section first),
    #    interpolate the CURRENT family registry and active spec vocabulary
    #    into it, and return (system_prompt, user_msg) where user_msg is just
    #    the normalized title key.
    #
    # TODO 2. Recommended approach:
    #    - The template contains two placeholder tokens, {{KNOWN_FAMILIES}}
    #      and {{ACTIVE_SPECS}}. Read the file, then str.replace() each token
    #      with a comma-separated join of the corresponding list.
    #    - Read the template through a small module-level helper wrapped in
    #      @functools.lru_cache() so the file is read from disk once per
    #      process, not once per title. (functools is already imported.)
    #    - user_msg should be the bare key string — the system prompt already
    #      explains what to do with it. Mirroring the skills extractor, keep
    #      all instructions in the system message.
    #
    # TODO 3. Implementation details:
    #    - Handle the empty-registry bootstrap case: if families is empty,
    #      substitute something like "(none yet — propose one)" rather than
    #      an empty string, so the prompt still reads coherently.
    #    - Do NOT interpolate with f-strings/format() over the whole template:
    #      the template contains literal JSON braces which format() would
    #      treat as placeholders. Plain .replace() of the two tokens is safer.
    #    - PROMPT_VERSION above identifies this template; if you edit the
    #      .txt file, bump the constant in the same commit.
    raise NotImplementedError


def call_title_llm(model: str, system_prompt: str, user_msg: str) -> dict:
    """One classification call to local Gemma via Ollama. Design §6.2."""
    # TODO 1. What to do:
    #    Send the prompt pair to Ollama and return the parsed JSON dict.
    #    Retry exactly once on unparseable output; raise TitleLLMError after
    #    the second failure (the caller — the orchestrator — decides what
    #    fallback means; this function does not).
    #
    # TODO 2. Recommended approach:
    #    Mirror Extractor.extract_skills_from_job (extractor.py):
    #        ollama.chat(model=model,
    #                    messages=[{"role": "system", ...},
    #                              {"role": "user", ...}],
    #                    format="json",
    #                    options={"temperature": 0})
    #    then json.loads(response["message"]["content"]) inside try/except
    #    json.JSONDecodeError. On failure, append a terse nudge to the user
    #    message — 'Return ONLY the JSON object.' — and call once more.
    #
    # TODO 3. Implementation details:
    #    - temperature=0 matters doubly here: decisions are memoized forever,
    #      so nondeterminism would make the taxonomy depend on which worker
    #      saw a title first.
    #    - format="json" makes Ollama constrain decoding to valid JSON — the
    #      retry mostly covers models wrapping output in markdown fences.
    #    - Log (log.warning) the raw content on the first parse failure; you
    #      will want that when tuning the prompt.
    #    - Let ollama's own connection errors propagate as-is — the
    #      orchestrator catches broadly and treats them as transient.
    raise NotImplementedError


def validate_decision(
    raw_out: dict, families: list[str], active_specs: list[str], conn
) -> TitleDecision:
    """Trust boundary between a 4B-parameter model and the database. §6.2."""
    # TODO 1. What to do:
    #    Take the raw dict the LLM returned and either shape it into a clean
    #    TitleDecision or degrade it to an abstention. Steps, in order:
    #      a. Schema check — exactly the keys {canonical_title: str,
    #         role_family: str|None, specializations: list[str]}; reject
    #         extra keys, missing keys, or wrong types.
    #      b. Normalize every string: lowercase, collapse whitespace; dedupe
    #         specializations while preserving order.
    #      c. Apply HEAD_NOUN_MAP to the LAST word of canonical_title
    #         (developer/programmer/swe → engineer) so spelling variants
    #         converge on one canonical row.
    #      d. role_family: if it's in `families` (or None) → accept. If it's
    #         a new name → treat as a proposal: register_new_family(), then
    #         accept it anyway.
    #      e. specs: any spec not in `active_specs` → register_new_spec(...,
    #         status='pending') but KEEP it on the decision — data first,
    #         curation later (§8 reviews pending specs).
    #      f. Sanity caps: more than MAX_SPECS specs or canonical_title longer
    #         than MAX_CANONICAL_WORDS words → drop the whole thing to an
    #         abstention (role_family=None) and log.warning. Better unmapped
    #         than polluted.
    #
    # TODO 2. Recommended approach:
    #    - Write a tiny local helper `_clean(s: str) -> str` for the
    #      lowercase+collapse step and reuse it on the canonical, the family,
    #      and every spec — one definition of "clean".
    #    - For the schema check, compare set(raw_out.keys()) against the
    #      expected set, then isinstance-check each value. On any violation
    #      raise TitleLLMError with a message that INCLUDES raw_out — the
    #      orchestrator logs it and abstains; you get a debuggable trail.
    #    - For (f), return TitleDecision.abstain(...) — but note abstain()
    #      wants the KEY, which this function doesn't receive. Two options:
    #      add a `key: str` parameter (recommended — cleaner logs), or raise
    #      TitleLLMError and let the orchestrator abstain. Pick one and be
    #      consistent with how you call it from the orchestrator.
    #
    # TODO 3. Implementation details:
    #    - "role_family may be null" arrives from JSON as Python None — your
    #      isinstance check must be `(str, type(None))`-shaped.
    #    - Dedupe specs with dict.fromkeys(specs) (preserves order), not set().
    #    - Registry lookups: convert `families`/`active_specs` to sets once at
    #      the top; you'll test membership up to 5 times.
    #    - The decision's specializations field is a tuple — convert at the
    #      very end when constructing TitleDecision.
    raise NotImplementedError


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator (design §6.2) — this is what processor.py and the backfill call
# ─────────────────────────────────────────────────────────────────────────────


class TitleNormalizer:
    """Per-worker facade: key → LRU → title_map → LLM → validate → upsert.

    Constructed once in Processor.__init__ (§6.4) and reused by the backfill
    script (§7) so both planes share exactly one code path.
    """

    def __init__(self, db, model: str = LLM_MODEL) -> None:
        # TODO 1. What to do:
        #    Store the collaborators and set up the two in-process caches:
        #      - self.db     : the SupabaseClient (its .conn is the psycopg
        #                      connection every module function above takes)
        #      - self.model  : the Ollama model tag
        #      - self._memo  : dict[str, TitleDecision] — the L1 LRU keyed on
        #                      the normalized title key
        #      - registry cache state for _families()/_specs() (see below)
        #
        # TODO 2. Recommended approach:
        #    - A plain dict is fine for the memo. functools.lru_cache is
        #      awkward here because the cached function would need `self` and
        #      a DB connection in its signature; an explicit dict is clearer
        #      and this table is small (O(distinct titles)).
        #    - For the registry cache, store tuples like
        #      self._families_cache: tuple[float, list[str]] | None
        #      holding (loaded_at_monotonic, values).
        #
        # TODO 3. Implementation details:
        #    - Also compute self.model_version here, e.g.
        #      f"{model}@{YYYY-MM of today}" — matches the schema comment
        #      example "gemma4:latest@2026-07" and is stamped on every upsert.
        #    - Don't preload anything from the DB in __init__; lazy-load on
        #      first use so constructing a TitleNormalizer stays cheap in
        #      tests.
        raise NotImplementedError

    def _families(self) -> list[str]:
        # TODO 1. What to do:
        #    Return the family registry, refreshing from the DB via
        #    load_family_registry() when the cached copy is older than
        #    REGISTRY_TTL_SECS (or absent).
        #
        # TODO 2. Recommended approach:
        #    if cache is None or time.monotonic() - loaded_at > TTL: reload.
        #    time is already imported; use time.monotonic(), not time.time(),
        #    for interval math (immune to clock adjustments).
        #
        # TODO 3. Implementation details:
        #    - Staleness is harmless by design (§6.2): worst case the LLM
        #      proposes a family that already exists, and ON CONFLICT
        #      DO NOTHING + reconcile absorb it. So no locking needed even
        #      though this worker is effectively single-threaded anyway.
        raise NotImplementedError

    def _specs(self) -> list[str]:
        # TODO: identical TTL pattern to _families(), backed by
        # load_spec_vocab(). Consider factoring the TTL logic into one small
        # private helper taking a loader callable, used by both.
        raise NotImplementedError

    def get_or_create_title_decision(
        self, raw_title: str, source: str = "ingest_llm"
    ) -> TitleDecision:
        """THE entry point. Never raises; never drops a posting. §6.2."""
        # TODO 1. What to do:
        #    Compose the full ladder for one raw title:
        #      1. key = normalize_title_key(raw_title)
        #         - if the key is empty ("" after cleaning) → return
        #           TitleDecision.abstain(key) immediately, no DB, no LLM.
        #      2. L1: self._memo hit? → return it.
        #      3. L2: lookup_title_map(self.db.conn, key) hit? → warm the L1
        #         memo, return it.
        #      4. Miss → build_normalizer_prompt(key, self._families(),
        #         self._specs()) → call_title_llm(...) →
        #         validate_decision(...) → upsert_title_map(..., source,
        #         self.model_version, PROMPT_VERSION) → memoize in L1 →
        #         return.
        #
        # TODO 2. Recommended approach:
        #    Wrap step 4 in try/except. On TitleLLMError OR any unexpected
        #    exception: log.error with the key and exception (loudly — this
        #    is the "LLM is down" signal), and return
        #    TitleDecision.abstain(key) WITHOUT raising. A title-normalization
        #    failure must never drop a posting (§6.2) — the posting simply
        #    lands unmapped and stays reachable through the fallback path.
        #
        # TODO 3. Implementation details:
        #    - CRITICAL asymmetry in what gets memoized (§6.2, §12):
        #        * transient failure (exception path) → do NOT upsert and do
        #          NOT put it in self._memo. The key stays unmapped in the DB
        #          so a later backfill/retry can fix it. (Skipping the L1 memo
        #          too means a recovered Ollama gets retried within the same
        #          worker lifetime — cheap and self-healing.)
        #        * deliberate abstention (LLM returned role_family: null and
        #          it validated) → DO upsert it. That's a real decision:
        #          "this is not a recognizable tech title", remembered forever.
        #    - Steps 2/3 are why this function is cheap: the LLM fires once
        #      per distinct normalized title EVER, across ingest and backfill.
        #    - Return type is always a TitleDecision — callers branch on
        #      decision.is_placed, never on exceptions.
        raise NotImplementedError
