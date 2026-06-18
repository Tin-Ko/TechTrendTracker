package services

import (
	"fmt"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/knights-analytics/hugot"
	"github.com/knights-analytics/hugot/options"
	"github.com/knights-analytics/hugot/pipelines"
)

// EmbeddingDim is the bge-small-en-v1.5 output dimension. Must match the
// vector(384) column in Supabase and the Python embedder.
const EmbeddingDim = 384

const (
	cacheTTL      = 30 * time.Minute
	cacheCapacity = 1024
)

type cacheEntry struct {
	vec       []float32
	expiresAt time.Time
}

type EmbedService struct {
	session    *hugot.Session
	pipeline   *pipelines.FeatureExtractionPipeline
	mu         sync.RWMutex
	cache      map[string]cacheEntry
	cacheOrder []string
}

var (
	embedOnce sync.Once
	embedSvc  *EmbedService
	embedErr  error
)

// InitEmbedService loads the ONNX model + tokenizer once. Path comes from
// ONNX_MODEL_DIR; the directory must contain model.onnx and tokenizer.json.
func InitEmbedService() error {
	embedOnce.Do(func() {
		modelDir := os.Getenv("ONNX_MODEL_DIR")
		if modelDir == "" {
			embedErr = fmt.Errorf("ONNX_MODEL_DIR not set")
			return
		}

		var sessionOpts []options.WithOption
		if ortPath := os.Getenv("ONNX_LIBRARY_PATH"); ortPath != "" {
			sessionOpts = append(sessionOpts, options.WithOnnxLibraryPath(ortPath))
		}
		session, err := hugot.NewORTSession(sessionOpts...)
		if err != nil {
			embedErr = fmt.Errorf("hugot session: %w", err)
			return
		}

		cfg := hugot.FeatureExtractionConfig{
			ModelPath: modelDir,
			Name:      "title-embedder",
			Options: []hugot.FeatureExtractionOption{
				pipelines.WithNormalization(),
			},
		}
		pipe, err := hugot.NewPipeline(session, cfg)
		if err != nil {
			embedErr = fmt.Errorf("hugot pipeline: %w", err)
			return
		}

		embedSvc = &EmbedService{
			session:  session,
			pipeline: pipe,
			cache:    make(map[string]cacheEntry, cacheCapacity),
		}
	})
	return embedErr
}

func GetEmbedService() (*EmbedService, error) {
	if embedSvc == nil {
		if err := InitEmbedService(); err != nil {
			return nil, err
		}
	}
	return embedSvc, nil
}

func normalizeQuery(q string) string {
	return strings.Join(strings.Fields(strings.ToLower(q)), " ")
}

// Embed returns the 384-d L2-normalized vector for the given text. Results
// are cached per normalized query for cacheTTL.
func (s *EmbedService) Embed(text string) ([]float32, error) {
	key := normalizeQuery(text)
	if v, ok := s.cacheGet(key); ok {
		return v, nil
	}

	out, err := s.pipeline.RunPipeline([]string{key})
	if err != nil {
		return nil, fmt.Errorf("embed: %w", err)
	}
	if len(out.Embeddings) == 0 || len(out.Embeddings[0]) != EmbeddingDim {
		return nil, fmt.Errorf("embed: unexpected output shape (%d embeddings, dim=%d)",
			len(out.Embeddings), embeddingLen(out))
	}

	vec := out.Embeddings[0]
	s.cachePut(key, vec)
	return vec, nil
}

func embeddingLen(out *pipelines.FeatureExtractionOutput) int {
	if len(out.Embeddings) == 0 {
		return 0
	}
	return len(out.Embeddings[0])
}

func (s *EmbedService) cacheGet(key string) ([]float32, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if e, ok := s.cache[key]; ok && time.Now().Before(e.expiresAt) {
		return e.vec, true
	}
	return nil, false
}

func (s *EmbedService) cachePut(key string, vec []float32) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if len(s.cache) >= cacheCapacity && len(s.cacheOrder) > 0 {
		oldest := s.cacheOrder[0]
		s.cacheOrder = s.cacheOrder[1:]
		delete(s.cache, oldest)
	}
	s.cache[key] = cacheEntry{vec: vec, expiresAt: time.Now().Add(cacheTTL)}
	s.cacheOrder = append(s.cacheOrder, key)
}

// VectorLiteral formats the vector for pgvector ('[v1,v2,...]'::vector).
func VectorLiteral(v []float32) string {
	var b strings.Builder
	b.Grow(len(v) * 10)
	b.WriteByte('[')
	for i, x := range v {
		if i > 0 {
			b.WriteByte(',')
		}
		fmt.Fprintf(&b, "%.6f", x)
	}
	b.WriteByte(']')
	return b.String()
}

// Close releases the ONNX session. Cloud Run normally tears down the process,
// but tests and graceful shutdowns benefit.
func (s *EmbedService) Close() error {
	if s.session != nil {
		return s.session.Destroy()
	}
	return nil
}
