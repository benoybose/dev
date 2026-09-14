from __future__ import annotations

from typing import Any


class EmbeddingDependencyError(RuntimeError):
    pass


class LocalEmbedder:
    """CPU-local sentence-transformers wrapper; never makes an API request."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingDependencyError("Install the embeddings extra to enable local embeddings") from exc
        self.model_name = model_name
        self.model: Any = SentenceTransformer(model_name, device="cpu")

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self.model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        return vectors.tolist()

