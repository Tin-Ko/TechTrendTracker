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

	// TODO(hierarchical search §9.1) 1. What to do:
	//    Load the title map and start its refresher here, next to the other
	//    service inits:
	//      services.LoadTitleMap(ctx)          — boot snapshot
	//      services.StartTitleMapRefresher(d)  — periodic swap
	// TODO 2. Recommended approach:
	//    Read TITLE_MAP_REFRESH_SECS (default 600) into a time.Duration and
	//    pass it in. Parse with strconv.Atoi; ignore garbage values and use
	//    the default.
	// TODO 3. Implementation details:
	//    - NON-FATAL on failure, unlike the two inits above: log.Printf the
	//      error and keep serving — search degrades to fallback-only until
	//      the refresher succeeds (§12 "cold start + map load"). Do NOT
	//      log.Fatalf here; a bad taxonomy deploy must not take search down.
	//    - Start the refresher even if the boot load failed — it IS the
	//      retry mechanism.

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
