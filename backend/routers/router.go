package routers

import (
	"net/http"
	"github.com/Tin-Ko/TechTrendTracker/handlers"
)


func New() *http.ServeMux {
	mux := http.NewServeMux()

	// API routes
	mux.HandleFunc("/chart", handlers.HandleGetChart)
	mux.HandleFunc("/skills", handlers.HandleGetTopSkills)
	mux.HandleFunc("/", handlers.HomeHandler)
	mux.HandleFunc("/test", handlers.TestHandler)

	// Static files
	staticFS := http.FileServer(http.Dir("frontend/static"))
	mux.Handle("/static/", http.StripPrefix("/static/", staticFS))

	return mux
}
