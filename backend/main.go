package main

import (
	"log"
	"net/http"
	"os"
	"github.com/Tin-Ko/TechTrendTracker/routers"
	"github.com/Tin-Ko/TechTrendTracker/utils"
)


func main() {
	// Initialize database
	err := utils.InitDB("localhost", "5432", "bartsuper", "abcd1234", "skillsDB")
	if err != nil {
		log.Fatal(err)
	}


	mux := routers.New()
	
	// Start server
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	log.Printf("Server starting at port %s\n", port)
	err = http.ListenAndServe(":" + port, mux)

	if err != nil {
		log.Fatalf("Server failed to start: %v\n", err)	
	}

}
