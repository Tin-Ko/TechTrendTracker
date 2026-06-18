package main

import (
	"log"
	"net/http"
	"os"

	"github.com/Tin-Ko/TechTrendTracker/routers"
	"github.com/Tin-Ko/TechTrendTracker/services"
	"github.com/Tin-Ko/TechTrendTracker/utils"
)

func main() {
	if err := utils.InitDB(); err != nil {
		log.Fatalf("DB init failed: %v", err)
	}

	if err := services.InitEmbedService(); err != nil {
		log.Fatalf("Embed service init failed: %v", err)
	}

	mux := routers.New()

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	log.Printf("Server starting at port %s\n", port)

	if err := http.ListenAndServe("0.0.0.0:"+port, mux); err != nil {
		log.Fatalf("Server failed to start: %v\n", err)
	}
}
