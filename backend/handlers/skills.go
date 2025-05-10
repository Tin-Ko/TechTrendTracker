package handlers

import (
	"encoding/json"
	"net/http"

	"github.com/Tin-Ko/TechTrendTracker/services"
	"github.com/Tin-Ko/TechTrendTracker/utils"
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

	w.Header().Set("Content-Type", "application/json")
	err = json.NewEncoder(w).Encode(skillsResponse)
	if err != nil {
		utils.HTMLError(w, http.StatusInternalServerError, "Failed to encode JSON")
	}
}
