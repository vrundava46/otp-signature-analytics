"""Index the knowledge base into the vector store (incremental)."""
from __future__ import annotations

from pathlib import Path
from typing import List

import config
from otp_sig.rag.chunking import Chunk, chunk_markdown
from otp_sig.rag.embeddings import get_embedder
from otp_sig.rag.retriever import get_store


def _load_chunks(kb_dir: Path) -> List[Chunk]:
    chunks: List[Chunk] = []
    for md in sorted(kb_dir.glob("*.md")):
        chunks.extend(chunk_markdown(md.read_text(), source=md.name))
    return chunks


def index_kb(kb_dir: Path | None = None) -> dict:
    kb_dir = kb_dir or config.KB_DIR
    chunks = _load_chunks(kb_dir)
    store = get_store()
    existing = store.existing_hashes()  # id -> hash

    new = [c for c in chunks if c.id not in existing]
    if not new:
        return {"indexed": 0, "total": store.count(), "skipped": len(chunks)}

    embedder = get_embedder()
    embeddings = embedder.encode([c.text for c in new])
    store.upsert(
        ids=[c.id for c in new],
        embeddings=embeddings,
        documents=[c.text for c in new],
        metadatas=[
            {"source": c.source, "section": c.section, "content_hash": c.content_hash}
            for c in new
        ],
    )
    store.persist()
    return {
        "indexed": len(new),
        "total": store.count(),
        "skipped": len(chunks) - len(new),
        "embedder": embedder.name,
    }


if __name__ == "__main__":
    print(index_kb())
