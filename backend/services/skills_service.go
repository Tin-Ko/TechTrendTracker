package services

import (
	"github.com/Tin-Ko/TechTrendTracker/utils"
)

type SkillsResponse struct {
	JobTitle string
	JobCount int
	SkillsCount int
	AllSkills []string
	Skills []Skill
}

type Skill struct {
	Name string
	Count int
	Percentage float32
}


func GetTopSkills(jobTitle string) (SkillsResponse, error) {
	var jobCount int
	var skills []Skill
	var allSkills []string

	topSkillRows, err := utils.DB.Query(`
		SELECT jss.skill, jss.count, jss.percentage, jc.job_count 
		FROM job_skill_stats jss 
		JOIN job_count jc ON jss.job_title = jc.job_title
		WHERE jss.job_title = $1
		ORDER BY jss.count DESC
		LIMIT 10
	`, jobTitle)

	if err != nil {
		return SkillsResponse{}, err
	}

	defer topSkillRows.Close()


	for topSkillRows.Next() {
		var s Skill
		if err := topSkillRows.Scan(&s.Name, &s.Count, &s.Percentage, &jobCount); err != nil {
			return SkillsResponse{}, err
		}
		skills = append(skills, s)
	}

	allSkillRows, err := utils.DB.Query(`
		SELECT skill FROM job_skill_stats WHERE job_title = $1 ORDER BY count DESC
	`, jobTitle)

	if err != nil {
		return SkillsResponse{}, err
	}

	defer allSkillRows.Close()

	for allSkillRows.Next() {
		var s string
		if err := allSkillRows.Scan(&s); err != nil {
			return SkillsResponse{}, err
		}
		allSkills = append(allSkills, s)
	}

	response := SkillsResponse{
		JobTitle: jobTitle,
		JobCount: jobCount,
		SkillsCount: len(allSkills),
		Skills: skills,
		AllSkills: allSkills,
	}

	return response, nil
}
