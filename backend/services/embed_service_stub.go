//go:build !onnx

package services

// Default (no-tag) build: a no-op EmbedService so the `services` package links
// without ONNX Runtime + libtokenizers. This is what CI, `go vet`, and
// `go test ./...` compile. Any attempt to actually embed returns an error — the
// stub is for building and testing the model-free logic (facets, set-cover,
// title parity), not for serving traffic. Real impl: embed_service_onnx.go
// (`-tags onnx`). Pure helpers live in embed_service.go (both builds).

import "fmt"

var errNoONNX = fmt.Errorf(
	"embed service unavailable: binary built without the 'onnx' build tag " +
		"(build/run with -tags onnx for the real ONNX embedder)")

// EmbedService is a stand-in with no ONNX/hugot dependency. Method set matches
// the real type so callers (skills_service.go) compile in both builds.
type EmbedService struct{}

func InitEmbedService() error { return errNoONNX }

func GetEmbedService() (*EmbedService, error) { return nil, errNoONNX }

func (s *EmbedService) Embed(text string) ([]float32, error) { return nil, errNoONNX }

func (s *EmbedService) Close() error { return nil }
