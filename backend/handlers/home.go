package handlers

import (
	"html/template"
	"net/http"

	"github.com/Tin-Ko/TechTrendTracker/utils"
)

// Handle GET /home
func HomeHandler(w http.ResponseWriter, r *http.Request) {
	tmpl, err := template.ParseFiles("frontend/templates/layout.html", "frontend/templates/index.html")
	if err != nil {
		utils.HTMLError(w, 500, "Template error")
		return
	}

	w.Header().Set("Content-Type", "text/html")

	err = tmpl.Execute(w, nil)
	if err != nil {
		utils.HTMLError(w, 500, "Execution error: " + err.Error())
		return
	}
}
