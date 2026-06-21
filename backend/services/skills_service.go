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

// GetTopSkills runs the hybrid query: ANN preselect -> trigram blend ->
// threshold -> unnest+GROUP BY for the top skills, plus all-skills and
// related-titles lookups against the same matched set.
func GetTopSkills(jobTitle string) (SkillsResponse, error) {
	if jobTitle == "" {
		return SkillsResponse{}, fmt.Errorf("missing job title")
	}

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
