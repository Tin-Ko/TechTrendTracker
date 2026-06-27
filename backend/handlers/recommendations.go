package handlers

import (
	"net/http"
	"strings"

	"github.com/Tin-Ko/TechTrendTracker/services"
	"github.com/Tin-Ko/TechTrendTracker/utils"
)

// Handle GET /recommendations?skills=React,Python,Java,JavaScript,C++
//
// The frontend passes the top skills it already got from /skills, so this stays
// a cheap catalog lookup — no embedding or hybrid retrieval re-run here.
func HandleGetRecommendations(w http.ResponseWriter, r *http.Request) {
	raw := r.URL.Query().Get("skills")
	if strings.TrimSpace(raw) == "" {
		utils.HTMLError(w, http.StatusBadRequest, "Missing skills parameter")
		return
	}

	var topSkills []string
	for _, s := range strings.Split(raw, ",") {
		if s = strings.TrimSpace(s); s != "" {
			topSkills = append(topSkills, s)
		}
	}

	resp, err := services.GetRecommendations(topSkills)
	if err != nil {
		utils.HTMLError(w, http.StatusInternalServerError, "Failed to fetch recommendations: "+err.Error())
		return
	}

	utils.JSON(w, http.StatusOK, resp)
}
