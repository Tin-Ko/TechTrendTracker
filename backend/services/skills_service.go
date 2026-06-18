package services

import (
	"context"
	"fmt"

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

// Hybrid retrieval constants. Two-stage:
//   1. ANN preselect: top annPoolSize postings by cosine similarity
//      (HNSW-accelerated).
//   2. Re-rank: blend vec_sim with pg_trgm similarity(job_title, query),
//      filter by combinedFloor, take top matchLimit.
//
// Trigram tolerance catches typos like "embeded" -> "embedded" that the
// bge-small subword tokenizer mishandles in pure-cosine mode.
// Two-stage retrieval, tuned against the current dataset (June 2026):
//   - "embedded software engineer"  -> only embedded postings, no SWE noise
//   - "embeded software engineer"   -> same (typo recovered via trigram)
//   - "software engineer"           -> broad SWE results
//
// Trigram is weighted higher than the vector because typos/substring matches
// are the failure case we're solving here. The 0.80 floor sits comfortably
// between the typo-case score for Embedded (~0.87) and SWE (~0.78).
//
// Sizing notes:
//   - `combinedFloor` is the real relevance filter.
//   - `annPoolSize` only bounds the HNSW candidate walk — it must stay
//     comfortably above the number of above-threshold matches any realistic
//     query produces; otherwise we silently drop relevant postings.
//   - `matchLimit` is a safety valve, NOT a "top K" knob. Set equal to
//     `annPoolSize` so the threshold does all the gating and every
//     above-threshold posting feeds the skill histogram.
// Revisit these once the dataset crosses ~10k postings or queries start to
// regularly produce more than ~1500 above-threshold matches.
const (
	annPoolSize   = 2000
	matchLimit    = 2000
	vectorWeight  = 0.4
	trgmWeight    = 0.6
	combinedFloor = 0.80
)

// matchedCTE is the shared two-stage matched-set SQL. Selects whatever
// columns the caller lists; the outer query then aggregates from `matched`.
// Bind vars: $1 query vector literal, $2 seniority filter (nullable),
// $3 year floor (nullable), $4 normalized query string for trigram.
const matchedCTE = `
WITH ann AS (
    SELECT posting_id, job_title, skills,
           1 - (title_embedding <=> $1::vector) AS vec_sim
    FROM job_postings
    WHERE ($2::text IS NULL OR seniority = $2 OR seniority = 'unknown')
      AND ($3::int  IS NULL OR posting_year >= $3)
    ORDER BY title_embedding <=> $1::vector
    LIMIT %d
),
scored AS (
    SELECT *,
           similarity(job_title, $4) AS trgm_sim,
           (%f * vec_sim + %f * similarity(job_title, $4)) AS combined
    FROM ann
),
matched AS (
    SELECT * FROM scored
    WHERE combined > %f
    ORDER BY combined DESC
    LIMIT %d
)`

func buildMatchedCTE() string {
	return fmt.Sprintf(matchedCTE, annPoolSize, vectorWeight, trgmWeight, combinedFloor, matchLimit)
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
