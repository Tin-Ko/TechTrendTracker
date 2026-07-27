package services

// Pure embedding helpers with NO ONNX/hugot dependency — compiled into BOTH the
// real (`-tags onnx`) and stub (default) builds. The model-bearing implementation
// is split by build tag: embed_service_onnx.go (real, cgo) vs
// embed_service_stub.go (no-op, so CI and bare `go build`/`go test` link without
// ONNX Runtime + libtokenizers). See implementation-plan.md D2.

import (
	"fmt"
	"strings"
)

// EmbeddingDim is the bge-small-en-v1.5 output dimension. Must match the
// vector(384) column in Supabase and the Python embedder.
const EmbeddingDim = 384

func normalizeQuery(q string) string {
	return strings.Join(strings.Fields(strings.ToLower(q)), " ")
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
