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

	// TODO(hierarchical search §9.3) 1. What to do:
	//    Nothing structural — the Resolved block rides along automatically
	//    once GetTopSkills fills it (the field is already on
	//    SkillsResponse and json.Encoder serializes it; nil until then).
	// TODO 2. Recommended approach:
	//    If you want display-ready names, title-case
	//    skillsResponse.Resolved.CanonicalTitle here (canonicals are stored
	//    lowercase; §9.2 says presentation is handler/frontend business,
	//    never SQL).
	// TODO 3. Implementation details:
	//    - Optional debug affordance for §11 phase 4 smoke tests: accept a
	//      ?search_mode=legacy|structured|auto query param here and thread
	//      it to the service to override SEARCH_MODE per request on staging.

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
