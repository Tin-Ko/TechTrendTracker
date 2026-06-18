"""Title embedder using bge-small-en-v1.5 exported to ONNX.

The Go backend embeds queries with the same ONNX artifact via `hugot`. To
keep vectors comparable across both planes the pipeline (tokenizer settings,
mean pooling, L2 normalization) must match on both sides — see search_design.md
section 5.2.

Usage:
    embedder = TitleEmbedder(model_dir=os.environ["ONNX_MODEL_DIR"])
    vec = embedder.embed("new grad backend engineer")   # -> list[float] of length 384
"""

from __future__ import annotations

import os
from typing import List

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer


EMBEDDING_DIM = 384
MAX_LEN = 128


class TitleEmbedder:
    def __init__(
        self,
        model_dir: str | None = None,
        onnx_filename: str = "model.onnx",
        tokenizer_filename: str = "tokenizer.json",
    ) -> None:
        model_dir = model_dir or os.environ.get("ONNX_MODEL_DIR")
        if not model_dir:
            raise ValueError(
                "ONNX_MODEL_DIR not set and model_dir not provided. Export "
                "bge-small-en-v1.5 to ONNX and point this at the directory."
            )

        self.model_dir = model_dir
        self.session = ort.InferenceSession(
            os.path.join(model_dir, onnx_filename),
            providers=["CPUExecutionProvider"],
        )
        self.tokenizer = Tokenizer.from_file(os.path.join(model_dir, tokenizer_filename))
        self.tokenizer.enable_truncation(max_length=MAX_LEN)
        self.tokenizer.enable_padding(length=MAX_LEN)

        self.input_names = {i.name for i in self.session.get_inputs()}

    def embed(self, text: str) -> List[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        encs = self.tokenizer.encode_batch(texts)
        input_ids = np.array([e.ids for e in encs], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encs], dtype=np.int64)

        feed = {"input_ids": input_ids, "attention_mask": attention_mask}
        if "token_type_ids" in self.input_names:
            feed["token_type_ids"] = np.zeros_like(input_ids)

        outputs = self.session.run(None, feed)
        token_embeds = outputs[0]  # (batch, seq_len, hidden)

        mask = attention_mask[..., None].astype(np.float32)
        summed = (token_embeds * mask).sum(axis=1)
        counts = np.clip(mask.sum(axis=1), a_min=1e-9, a_max=None)
        pooled = summed / counts

        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        normalized = pooled / np.clip(norms, a_min=1e-12, a_max=None)

        return normalized.astype(np.float32).tolist()


if __name__ == "__main__":
    embedder = TitleEmbedder()
    vec = embedder.embed("new grad backend engineer")
    print(f"dim={len(vec)} first5={vec[:5]}")
