from __future__ import annotations

from pathlib import Path
from typing import Any


class EmbeddingDependencyError(RuntimeError):
    pass


class LocalEmbedder:
    """CPU-local sentence-transformers wrapper; never makes an API request."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
                 cache_dir: Path | None = None, local_files_only: bool = False):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingDependencyError("Install the embeddings extra to enable local embeddings") from exc
        self.model_name = model_name
        self.cache_dir = Path(cache_dir).expanduser() if cache_dir else None
        self.local_files_only = local_files_only
        kwargs: dict[str, Any] = {"device": "cpu"}
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            kwargs["cache_folder"] = str(self.cache_dir)
        if local_files_only:
            kwargs["local_files_only"] = True
        try:
            self.model: Any = SentenceTransformer(model_name, **kwargs)
        except TypeError:
            kwargs.pop("local_files_only", None)
            self.model = SentenceTransformer(model_name, **kwargs)

    @property
    def identity(self) -> str:
        """Stable cache namespace for this embedding model."""
        return self.model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self.model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        return vectors.tolist()
