package services

import (
	"context"
	"fmt"

	"github.com/Tin-Ko/TechTrendTracker/utils"
	"github.com/lib/pq"
)

type ProjectRec struct {
	Title  string
	Level  string
	Blurb  string
	Skills []string
}

type RecommendationsResponse struct {
	TopSkills []string
	Projects  []ProjectRec
}

const (
	// A search contributes at most this many skills to the match; each catalog
	// project covers exactly 3 of them.
	topSkillsUsed = 5
	minProjects   = 3
	maxProjects   = 4
)

type candidate struct {
	rec   ProjectRec
	score float64
}

// GetRecommendations returns 3-4 portfolio projects from the offline catalog
// (project_recommendations, built by data_pipeline/recommendations). Every
// candidate's 3-skill triple is a subset of the searched top skills
// (`skills <@ $top`); a greedy set-cover selection then picks projects so they
// together span as many of the top skills as possible while each stays focused
// on 3 of them. No model runs here — it's a pure catalog lookup.
func GetRecommendations(topSkills []string) (RecommendationsResponse, error) {
	if len(topSkills) > topSkillsUsed {
		topSkills = topSkills[:topSkillsUsed]
	}
	// A triple needs at least 3 skills to be a subset of anything.
	if len(topSkills) < 3 {
		return RecommendationsResponse{TopSkills: topSkills, Projects: []ProjectRec{}}, nil
	}

	cands, err := fetchCandidates(topSkills)
	if err != nil {
		return RecommendationsResponse{}, err
	}

	return RecommendationsResponse{
		TopSkills: topSkills,
		Projects:  selectByCoverage(cands, len(topSkills)),
	}, nil
}

func fetchCandidates(topSkills []string) ([]candidate, error) {
	// skills <@ $1: keep catalog projects whose whole triple is contained in
	// the searched top skills. GIN index idx_pr_skills serves this.
	const q = `
SELECT title, level, blurb, skills, score
FROM project_recommendations
WHERE skills <@ $1
ORDER BY score DESC;`

	rows, err := utils.DB.QueryContext(context.Background(), q, pq.Array(topSkills))
	if err != nil {
		return nil, fmt.Errorf("recommendations query: %w", err)
	}
	defer rows.Close()

	var out []candidate
	for rows.Next() {
		var c candidate
		if err := rows.Scan(
			&c.rec.Title, &c.rec.Level, &c.rec.Blurb,
			pq.Array(&c.rec.Skills), &c.score,
		); err != nil {
			return nil, err
		}
		out = append(out, c)
	}
	return out, rows.Err()
}

// selectByCoverage greedily picks up to maxProjects candidates. Each step takes
// the one covering the most still-uncovered top skills; ties resolve to higher
// score because the input is already score-sorted and the scan keeps the first
// max it sees. Once every top skill is covered it stops as soon as minProjects
// is met, and it won't add a project that covers nothing new past the minimum.
func selectByCoverage(cands []candidate, topSkillCount int) []ProjectRec {
	covered := make(map[string]bool)
	used := make(map[int]bool)
	picked := make([]ProjectRec, 0, maxProjects)

	for len(picked) < maxProjects && len(used) < len(cands) {
		bestIdx, bestGain := -1, -1
		for i, c := range cands {
			if used[i] {
				continue
			}
			gain := 0
			for _, s := range c.rec.Skills {
				if !covered[s] {
					gain++
				}
			}
			if gain > bestGain {
				bestIdx, bestGain = i, gain
			}
		}
		if bestIdx == -1 {
			break
		}
		// Don't pad with projects that add no new coverage once we have enough.
		if bestGain == 0 && len(picked) >= minProjects {
			break
		}

		used[bestIdx] = true
		for _, s := range cands[bestIdx].rec.Skills {
			covered[s] = true
		}
		picked = append(picked, cands[bestIdx].rec)

		if len(covered) >= topSkillCount && len(picked) >= minProjects {
			break
		}
	}
	return picked
}
