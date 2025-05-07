package handlers

import (
	"net/http"
	"github.com/Tin-Ko/TechTrendTracker/services"
	"github.com/Tin-Ko/TechTrendTracker/utils"
	"html/template"
)

// Handle GET /skills
func HandleGetTopSkills(w http.ResponseWriter, r *http.Request) {
	// Get job title from query parameters
	jobTitle := r.URL.Query().Get("job_title")

	if jobTitle == "" {
		utils.HTMLError(w, http.StatusBadRequest, "Missing job_title parameter")
		return
	}

	// Call service
	skillsResponse, err := services.GetTopSkills(jobTitle)
	if err != nil {
		utils.HTMLError(w, http.StatusInternalServerError, "Failed to fetch top skills: " + err.Error())
		return
	}

	// Create template
	tmpl, err := template.ParseFiles("frontend/templates/skills_partial.html")
	if err != nil {
		utils.HTMLError(w, 500, "Template error: " + err.Error())
	}

	w.Header().Set("Content-Type", "text/html")

	// Respond with HTML
	tmpl.Execute(w, skillsResponse)
}
