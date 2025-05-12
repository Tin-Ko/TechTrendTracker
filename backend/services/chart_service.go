package services

import (
	"github.com/Tin-Ko/TechTrendTracker/utils"
)

type ChartResponse struct {
	JobTitle string
	JobCount int
	SkillCount int
}

func GetChartData(jobTitle string) (ChartResponse, error) {
	var jobCount int
	var skillCount int

	rows, err := utils.DB.Query(`
		SELECT jc.job_count, COUNT(DISTINCT jss.skill) AS skill_count
		FROM job_count jc
		JOIN job_skill_stats jss ON jss.job_title = jc.job_title
		WHERE jss.job_title = $1
		GROUP BY jc.job_title
	`, jobTitle)

	if err != nil {
		return ChartResponse{}, err
	}

	defer rows.Close()

	for rows.Next() {
		if err := rows.Scan(&jobCount, &skillCount); err != nil {
			return ChartResponse{}, err
		}
	}

	response := ChartResponse{
		JobTitle: jobTitle,
		JobCount: jobCount,
		SkillCount: skillCount,
	}

	return response, nil
}
