from __future__ import annotations

from pathlib import Path


def select_relevant_files(query: str, candidate_files: list[Path], max_files: int = 5, embedder=None) -> list[Path]:
    """Select files deterministically; use optional embeddings when supplied."""
    if len(candidate_files) <= max_files:
        return candidate_files
    if embedder is not None:
        try:
            q = embedder.embed([query])[0]
            contents = []
            for path in candidate_files:
                with path.open("rb") as stream:
                    contents.append(stream.read(2000).decode("utf-8", errors="ignore"))
            vectors = embedder.embed(contents)
            try:
                import numpy as np

                scores = list(np.asarray(vectors) @ np.asarray(q))
            except ImportError:
                scores = [sum(a * b for a, b in zip(v, q)) for v in vectors]
            return [candidate_files[i] for i in sorted(range(len(candidate_files)), key=lambda i: scores[i], reverse=True)[:max_files]]
        except (OSError, TypeError, ValueError):
            pass
    terms = {word.lower() for word in query.split() if len(word) > 2}
    scored = []
    for index, path in enumerate(candidate_files):
        text = path.name.lower()
        scored.append((sum(term in text for term in terms), -index, path))
    return [item[2] for item in sorted(scored, reverse=True)[:max_files]]


def read_context(files: list[Path], max_file_bytes: int = 1_000_000, max_total_bytes: int = 5_000_000) -> str:
    chunks: list[str] = []
    total = 0
    for path in files:
        if total >= max_total_bytes:
            break
        try:
            with path.open("rb") as stream:
                content = stream.read(max_file_bytes).decode("utf-8", errors="replace")
        except OSError:
            continue
        remaining = max_total_bytes - total
        header = f"\n--- {path} ---\n"
        header_bytes = header.encode("utf-8")
        if len(header_bytes) >= remaining:
            chunks.append(header_bytes[:remaining].decode("utf-8", errors="ignore"))
            total = max_total_bytes
            break
        remaining_content = max(0, remaining - len(header.encode("utf-8")))
        content = content.encode("utf-8")[:remaining_content].decode("utf-8", errors="ignore")
        chunks.append(header + content)
        total += len(header.encode("utf-8")) + len(content.encode("utf-8"))
    return "".join(chunks)
