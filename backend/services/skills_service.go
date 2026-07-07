package services

import (
	"context"
	"fmt"
	"strconv"
	"strings"

	"github.com/Tin-Ko/TechTrendTracker/utils"
)

type SkillsResponse struct {
	JobTitle      string
	JobCount      int
	SkillsCount   int
	AllSkills     []string
	Skills        []Skill
	RelatedTitles []string
	// Resolved explains HOW this query was matched (design §9.3): nil until
	// hierarchical search is wired in. Frontend renders it as the optional
	// "Showing: backend engineer · family: software engineer" caption.
	Resolved *ResolvedInfo
}

// ResolvedInfo is the §9.3 response block. Populate from the QueryPlan in
// GetTopSkills once the structured path is live.
type ResolvedInfo struct {
	CanonicalTitle  string
	RoleFamily      string
	Specializations []string
	MatchMode       string // "structured" | "fallback"
}

type Skill struct {
	Name       string
	Count      int
	Percentage float32
}

// Hybrid retrieval constants. Two retrievers run independently, then merge:
//   1. semantic_search: top `semanticPoolSize` postings by cosine similarity
//      (HNSW-accelerated via the pgvector index).
//   2. lexical_search:  top `lexicalPoolSize` postings by pg_trgm similarity,
//      gated by `job_title % $4` so the GIN trigram index does the heavy
//      lifting instead of a sequential similarity() scan.
//   3. FULL OUTER JOIN on posting_id; missing scores coalesce to 0.
//   4. Filter by combinedFloor, take top matchLimit, aggregate skills.
//
// Trigram weight > vector weight because typos/substring matches are the
// failure case (e.g. "embeded" → can't reach Embedded SE via embedding alone).
//
// Note on the 0.80 floor under FULL OUTER JOIN semantics: postings that
// appear in only ONE pool get the missing signal scored as 0, so they
// effectively need to be strong on the present signal AND meet the floor.
// This is intentional — both signals are required to clear the bar.
const (
	semanticPoolSize = 500
	lexicalPoolSize  = 500
	matchLimit       = 2000
	vectorWeight     = 0.4
	trgmWeight       = 0.6
	combinedFloor    = 0.80
)

// matchedCTETemplate is the shared hybrid matched-set SQL. The outer query
// aggregates from `matched`. Constant numeric values get substituted in via
// strings.Replacer (not fmt.Sprintf — the `%` in `job_title % $4` is the
// pg_trgm operator and would collide with format verbs).
//
// Postgres bind vars passed at query time:
//   $1 query vector literal
//   $2 seniority filter (nullable)
//   $3 year floor (nullable)
//   $4 normalized query string for trigram
const matchedCTETemplate = `
WITH semantic_search AS (
    -- top-K by cosine similarity (HNSW-indexed)
    SELECT posting_id, job_title, skills,
           1 - (title_embedding <=> $1::vector) AS vec_sim
    FROM job_postings
    WHERE ($2::text IS NULL OR seniority = $2 OR seniority = 'unknown')
      AND ($3::int  IS NULL OR posting_year >= $3)
    ORDER BY title_embedding <=> $1::vector
    LIMIT {{SEMANTIC_LIMIT}}
),
lexical_search AS (
    -- top-K by trigram similarity (GIN-indexed via the % operator)
    SELECT posting_id, job_title, skills,
           similarity(job_title, $4) AS trgm_sim
    FROM job_postings
    WHERE ($2::text IS NULL OR seniority = $2 OR seniority = 'unknown')
      AND ($3::int  IS NULL OR posting_year >= $3)
      AND job_title % $4
    ORDER BY similarity(job_title, $4) DESC
    LIMIT {{LEXICAL_LIMIT}}
),
combined_results AS (
    -- merge by posting_id; postings in only one pool get the missing signal as 0
    SELECT
        COALESCE(s.posting_id, l.posting_id) AS posting_id,
        COALESCE(s.job_title,  l.job_title)  AS job_title,
        COALESCE(s.skills,     l.skills)     AS skills,
        COALESCE(s.vec_sim,  0)              AS vec_sim,
        COALESCE(l.trgm_sim, 0)              AS trgm_sim,
        ({{VEC_W}}  * COALESCE(s.vec_sim, 0)
       + {{TRGM_W}} * COALESCE(l.trgm_sim, 0)) AS combined
    FROM semantic_search s
    FULL OUTER JOIN lexical_search l ON s.posting_id = l.posting_id
),
matched AS (
    SELECT * FROM combined_results
    WHERE combined > {{FLOOR}}
    ORDER BY combined DESC
    LIMIT {{MATCH_LIMIT}}
)`

func buildMatchedCTE() string {
	r := strings.NewReplacer(
		"{{SEMANTIC_LIMIT}}", strconv.Itoa(semanticPoolSize),
		"{{LEXICAL_LIMIT}}",  strconv.Itoa(lexicalPoolSize),
		"{{VEC_W}}",          strconv.FormatFloat(vectorWeight, 'f', 4, 64),
		"{{TRGM_W}}",         strconv.FormatFloat(trgmWeight, 'f', 4, 64),
		"{{FLOOR}}",          strconv.FormatFloat(combinedFloor, 'f', 4, 64),
		"{{MATCH_LIMIT}}",    strconv.Itoa(matchLimit),
	)
	return r.Replace(matchedCTETemplate)
}

// ── Hierarchical search: structured retrieval (design §9.2) ─────────────────
//
// Threshold philosophy shift, on purpose: the structured arm has NO relevance
// floor at all — membership is decided by the title map, not by an
// uncalibrated similarity score. The 0.80 blended floor only survives inside
// the legacy fallback CTE above.
const (
	// unmappedSemanticFloor gates the recall patch: postings the LLM
	// abstained on are rescued only when embedding-similar to the query.
	// This pool shrinks toward empty as taxonomy coverage → 100%.
	unmappedSemanticFloor = 0.86
	unmappedPoolSize      = 200
)

// structuredMatchedCTETemplate is the asymmetric-rule matched set (§3, §9.2).
// Bind vars at query time:
//   $1 role_family        $2 specializations (text[], via pq.Array)
//   $3 seniority filter   $4 year floor       $5 query vector literal
const structuredMatchedCTETemplate = `
WITH matched AS (
    -- primary: the asymmetric rule, pure index hits.
    -- specializations @> $2 means: every QUERY spec must be present on the
    -- posting; posting extras never disqualify (§3 containment direction).
    SELECT posting_id, job_title, canonical_title, skills
    FROM job_postings
    WHERE role_family = $1
      AND specializations @> $2::text[]
      AND ($3::text IS NULL OR seniority = $3 OR seniority = 'unknown')
      AND ($4::int  IS NULL OR posting_year >= $4)

    UNION ALL

    -- recall patch: postings the LLM couldn't place, rescued by embedding
    -- similarity so abstentions never 404 (§5.1, §12).
    SELECT posting_id, job_title, canonical_title, skills
    FROM job_postings
    WHERE role_family IS NULL
      AND ($3::text IS NULL OR seniority = $3 OR seniority = 'unknown')
      AND ($4::int  IS NULL OR posting_year >= $4)
      AND 1 - (title_embedding <=> $5::vector) > {{UNMAPPED_FLOOR}}
    ORDER BY title_embedding <=> $5::vector
    LIMIT {{UNMAPPED_POOL}}
)`

func buildStructuredMatchedCTE() string {
	// TODO 1. What to do:
	//    Substitute {{UNMAPPED_FLOOR}} and {{UNMAPPED_POOL}} into
	//    structuredMatchedCTETemplate and return the SQL.
	//
	// TODO 2. Recommended approach:
	//    Mirror buildMatchedCTE above verbatim: strings.NewReplacer +
	//    strconv.FormatFloat/Itoa. Same trick for the same reason — the
	//    template contains the `@>` and `%`-family operators, which
	//    fmt.Sprintf would mangle as format verbs.
	//
	// TODO 3. Implementation details:
	//    - 'f' format with 4 decimals for the float, matching the sibling.
	return "" // TODO: stub
}

// fetchRelatedTitlesStructured replaces fetchRelatedTitles on the structured
// path (§9.2): grouping by canonical_title turns near-duplicate raw strings
// ("Sr. Backend Engineer", "Backend Engineer (Remote)") into clean canonical
// names with meaningful counts.
func fetchRelatedTitlesStructured(ctx context.Context, plan QueryPlan, queryVec string, seniority *string, year *int) ([]string, error) {
	// TODO 1. What to do:
	//    buildStructuredMatchedCTE() + `
	//    SELECT COALESCE(canonical_title, job_title) AS t
	//    FROM matched
	//    GROUP BY t
	//    ORDER BY COUNT(*) DESC
	//    LIMIT 8;`
	//    (COALESCE because recall-patch rows may have NULL canonical_title.)
	//
	// TODO 2. Recommended approach:
	//    Copy the row-scanning shape of fetchRelatedTitles below. Bind args
	//    in template order: plan.Decision.Family, pq.Array(plan.Decision.Specs),
	//    seniority, year, queryVec. pq is "github.com/lib/pq" — already in
	//    go.mod; add the import when you first use it.
	//
	// TODO 3. Implementation details:
	//    - pq.Array(nil) sends NULL, not '{}' — always pass a non-nil slice
	//      (an empty []string{} is the correct "no specs" value, and
	//      `x @> '{}'` is true for every row, which is exactly the wide-net
	//      semantics for generic queries like "software engineer").
	//    - Canonicals are stored lowercase; title-case them for display in
	//      the handler or frontend (§9.2 says display-side, not SQL).
	return nil, nil // TODO: stub
}

// GetTopSkills runs the hybrid query: ANN preselect -> trigram blend ->
// threshold -> unnest+GROUP BY for the top skills, plus all-skills and
// related-titles lookups against the same matched set.
func GetTopSkills(jobTitle string) (SkillsResponse, error) {
	if jobTitle == "" {
		return SkillsResponse{}, fmt.Errorf("missing job title")
	}

	// TODO(hierarchical search §9.2) 1. What to do:
	//    Turn this function into the mode branch:
	//      plan := ResolveQuery(jobTitle)
	//      - still embed the query ONCE (the vector is needed by BOTH arms:
	//        recall patch on structured, semantic pool on fallback);
	//      - if plan.Mode == ModeStructured: run the SAME aggregation SQL
	//        bodies below but prefixed with buildStructuredMatchedCTE() and
	//        bound with (plan.Decision.Family, pq.Array(plan.Decision.Specs),
	//        seniorityFilter, facets.Year, queryVec); use
	//        fetchRelatedTitlesStructured for related titles;
	//      - else: exactly the code below, unchanged (legacy arm, kept
	//        verbatim as the §11 fallback — do not delete or "improve" it);
	//      - either way fill resp.Resolved from the plan.
	// TODO 2. Recommended approach:
	//    - Use plan.Facets instead of re-running ParseFacets below —
	//      ResolveQuery already parsed them; one facts source per request.
	//    - Gate the branch behind SEARCH_MODE (legacy|structured|auto,
	//      default legacy — §11 phase 4): read the env var once at package
	//      init; "auto" means structured-when-resolved, i.e. plan.Mode
	//      already encodes it, so "legacy" simply forces the else-arm.
	//    - The downstream aggregation SQL (top-10, all-skills) only reads
	//      FROM matched — it works untouched on top of either CTE. That
	//      was the point of the CTE seam.
	// TODO 3. Implementation details:
	//    - The two arms take different bind args ($1..$5 mean different
	//      things) — build one args []interface{} per arm next to its CTE
	//      choice; do not try to share the slice.
	//    - Log the §9.3 line here: mode=..., key=... (slog/log.Printf) —
	//      fallback-rate is the feature's health metric.

	embedder, err := GetEmbedService()
	if err != nil {
		return SkillsResponse{}, fmt.Errorf("embed init: %w", err)
	}
	vec, err := embedder.Embed(jobTitle)
	if err != nil {
		return SkillsResponse{}, fmt.Errorf("embed query: %w", err)
	}
	queryVec := VectorLiteral(vec)
	queryNorm := normalizeQuery(jobTitle)

	facets := ParseFacets(jobTitle)
	var seniorityFilter *string
	if facets.Seniority != "unknown" {
		s := facets.Seniority
		seniorityFilter = &s
	}

	ctx := context.Background()

	aggSQL := buildMatchedCTE() + `,
job_total AS (
    SELECT COUNT(*)::int AS n FROM matched
)
SELECT skill,
       COUNT(*)::int AS cnt,
       ROUND(100.0 * COUNT(*)::numeric / NULLIF((SELECT n FROM job_total), 0), 2)::float8 AS pct,
       (SELECT n FROM job_total) AS job_total
FROM matched, unnest(skills) AS skill
GROUP BY skill
ORDER BY cnt DESC
LIMIT 10;`

	rows, err := utils.DB.QueryContext(ctx, aggSQL, queryVec, seniorityFilter, facets.Year, queryNorm)
	if err != nil {
		return SkillsResponse{}, fmt.Errorf("agg query: %w", err)
	}
	defer rows.Close()

	var skills []Skill
	var jobCount int
	for rows.Next() {
		var s Skill
		var pct float64
		if err := rows.Scan(&s.Name, &s.Count, &pct, &jobCount); err != nil {
			return SkillsResponse{}, err
		}
		s.Percentage = float32(pct)
		skills = append(skills, s)
	}
	if err := rows.Err(); err != nil {
		return SkillsResponse{}, err
	}

	allSkills, err := fetchAllSkills(ctx, queryVec, seniorityFilter, facets.Year, queryNorm)
	if err != nil {
		return SkillsResponse{}, err
	}

	related, err := fetchRelatedTitles(ctx, queryVec, seniorityFilter, facets.Year, queryNorm)
	if err != nil {
		return SkillsResponse{}, err
	}

	return SkillsResponse{
		JobTitle:      jobTitle,
		JobCount:      jobCount,
		SkillsCount:   len(allSkills),
		Skills:        skills,
		AllSkills:     allSkills,
		RelatedTitles: related,
	}, nil
}

func fetchAllSkills(ctx context.Context, queryVec string, seniority *string, year *int, queryNorm string) ([]string, error) {
	rows, err := utils.DB.QueryContext(ctx, buildMatchedCTE()+`
SELECT skill
FROM matched, unnest(skills) AS skill
GROUP BY skill
ORDER BY COUNT(*) DESC;`, queryVec, seniority, year, queryNorm)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []string
	for rows.Next() {
		var s string
		if err := rows.Scan(&s); err != nil {
			return nil, err
		}
		out = append(out, s)
	}
	return out, rows.Err()
}

func fetchRelatedTitles(ctx context.Context, queryVec string, seniority *string, year *int, queryNorm string) ([]string, error) {
	rows, err := utils.DB.QueryContext(ctx, buildMatchedCTE()+`
SELECT job_title
FROM matched
GROUP BY job_title
ORDER BY COUNT(*) DESC
LIMIT 8;`, queryVec, seniority, year, queryNorm)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var titles []string
	for rows.Next() {
		var t string
		if err := rows.Scan(&t); err != nil {
			return nil, err
		}
		titles = append(titles, t)
	}
	return titles, rows.Err()
}
