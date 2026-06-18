package routers

import (
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/Tin-Ko/TechTrendTracker/handlers"
)

// FRONTEND_DIST overrides the default location of the Vite build output
// the backend serves in prod. Defaults to ../frontend/dist (relative to
// the backend cwd) so `cd backend && go run .` works during local dev too.
func New() *http.ServeMux {
	mux := http.NewServeMux()

	// JSON API
	mux.HandleFunc("/skills", handlers.HandleGetTopSkills)

	// SPA static files + history-mode fallback. Any GET that isn't an API
	// route falls through to here: try to serve a real file under
	// $FRONTEND_DIST, otherwise return index.html so React Router can take
	// over client-side.
	dist := os.Getenv("FRONTEND_DIST")
	if dist == "" {
		dist = "../frontend/dist"
	}
	mux.Handle("/", spaHandler(dist))

	return mux
}

func spaHandler(distDir string) http.Handler {
	fs := http.FileServer(http.Dir(distDir))
	indexPath := filepath.Join(distDir, "index.html")

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Strip the leading slash to map URL path to filesystem path.
		urlPath := strings.TrimPrefix(r.URL.Path, "/")
		full := filepath.Join(distDir, urlPath)

		// Containment check: don't let "../" escape the dist root.
		absDist, err1 := filepath.Abs(distDir)
		absFull, err2 := filepath.Abs(full)
		if err1 != nil || err2 != nil || !strings.HasPrefix(absFull, absDist) {
			http.NotFound(w, r)
			return
		}

		// If the path resolves to an actual file in dist, serve it.
		if info, err := os.Stat(full); err == nil && !info.IsDir() {
			fs.ServeHTTP(w, r)
			return
		}

		// Otherwise, hand back index.html so the SPA router handles it.
		http.ServeFile(w, r, indexPath)
	})
}
