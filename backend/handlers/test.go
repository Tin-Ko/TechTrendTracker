package handlers

import (
	"net/http"

	"github.com/Tin-Ko/TechTrendTracker/services"
	"github.com/Tin-Ko/TechTrendTracker/utils"
)

// Handle GET /home
func TestHandler(w http.ResponseWriter, r *http.Request) {
	
	// Call service
	testResponse, err := services.TestService()
	if err != nil {
		utils.HTMLError(w, http.StatusInternalServerError, "Test failed: " + err.Error())
		return
	}

	w.Write([]byte(testResponse))

}
