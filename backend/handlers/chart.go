package handlers

import (
	"fmt"
	"html/template"
	"net/http"

	"github.com/Tin-Ko/TechTrendTracker/services"
	"github.com/Tin-Ko/TechTrendTracker/utils"
)

// Handle GET /chart
func HandleGetChart(w http.ResponseWriter, r *http.Request) {
	jobTitle := r.URL.Query().Get("job_title")

	// Call service
	chartResponse, err := services.GetChartData(jobTitle)
	if err != nil {
		utils.HTMLError(w, http.StatusInternalServerError, "Failed to fetch chart data: " + err.Error())
	}

	// Create template
	tmpl, err := template.ParseFiles("frontend/templates/layout.html", "frontend/templates/chart_page.html")
	if err != nil {
		utils.HTMLError(w, 500, "Template error: " + err.Error())
		fmt.Println("Template error: ", err.Error())
		return
	}

	w.Header().Set("Content-Type", "text/html")

	// Respond with HTML
	err = tmpl.Execute(w, chartResponse)
	if err != nil {
		utils.HTMLError(w, 500, "Execution error: " + err.Error())
		fmt.Println("Execution error: ", err.Error())
		return
	}
}
