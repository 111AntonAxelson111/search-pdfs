"""Simple local PDF chunk index backed by one SQLite database.

Dependencies:
    pip install pymupdf numpy sentence-transformers

The database stores only:
    - each PDF's path relative to TARGET_PDF_DIR
    - each chunk's text, page range, and (later) embedding

It does NOT store a second copy of the full document or a separate pages table.
"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

import fitz  # PyMuPDF
import numpy as np

import os

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Change this to the root folder containing your PDFs.
TARGET_PDF_DIR = Path(r"C:\Users\anton\lokal\pdfs")

# One database file, next to this script.
DB_PATH = Path(__file__).resolve().with_name("pdf_index.sqlite3")

# Approximate maximum chunk size. A chunk can contain one or several pages.
MAX_CHUNK_CHARS = 3_500

# Number of chunks sent to the embedding function per batch.
EMBEDDING_BATCH_SIZE = 32

# Number of stored vectors read at a time during similarity search.
SEARCH_BATCH_SIZE = 512


# The embedding function you provide later must have this interface:
#     embed_texts(["text 1", "text 2"]) -> np.ndarray with shape (N, D)
EmbedTexts = Callable[[list[str]], np.ndarray]
EMBEDDING_MODEL_NAME = (
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

@contextmanager
def open_db() -> Iterator[sqlite3.Connection]:
    """Open the database and ensure connections are always closed."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
    finally:
        conn.close()


def initialise_db() -> None:
    """Create the small schema if it does not already exist."""
    with open_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id            INTEGER PRIMARY KEY,
                relative_path TEXT NOT NULL UNIQUE,
                file_hash     TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chunks (
                id          INTEGER PRIMARY KEY,
                document_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                page_start  INTEGER NOT NULL,
                page_end    INTEGER NOT NULL,
                text        TEXT NOT NULL,
                embedding   BLOB,

                UNIQUE (document_id, chunk_index),

                FOREIGN KEY (document_id)
                    REFERENCES documents(id)
                    ON DELETE CASCADE,

                CHECK (page_start >= 1),
                CHECK (page_end >= page_start)
            );

            CREATE INDEX IF NOT EXISTS idx_chunks_document
                ON chunks(document_id);

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )


# ---------------------------------------------------------------------------
# PDF reading and chunking
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    """Return a content hash, so unchanged PDFs do not need re-indexing."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_pdf_pages(pdf_path: Path) -> list[tuple[int, str]]:
    """Extract text page by page. Page numbers returned are 1-based."""
    pages: list[tuple[int, str]] = []

    with fitz.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf, start=1):
            text = page.get_text("text").strip()
            if text:
                pages.append((page_number, text))

    return pages


def split_long_text(text: str, max_chars: int) -> list[str]:
    """Split a single long page into chunks, preferring whitespace boundaries."""
    parts: list[str] = []
    start = 0

    while start < len(text):
        end = min(start + max_chars, len(text))

        if end < len(text):
            # Avoid creating a tiny fragment just to find a word boundary.
            boundary = text.rfind(" ", start + int(max_chars * 0.6), end)
            if boundary > start:
                end = boundary

        part = text[start:end].strip()
        if part:
            parts.append(part)
        start = end

    return parts


def make_chunks(
    pages: list[tuple[int, str]],
    max_chars: int = MAX_CHUNK_CHARS,
) -> list[tuple[int, int, str]]:
    """Create chunks while retaining each chunk's source page range.

    A chunk normally contains one or more complete pages. If one page is
    longer than max_chars, that page is split into multiple chunks, each of
    which maps to that same page number.

    Returns tuples: (page_start, page_end, chunk_text).
    """
    chunks: list[tuple[int, int, str]] = []
    buffer: list[str] = []
    buffer_chars = 0
    buffer_start: int | None = None
    buffer_end: int | None = None

    def flush_buffer() -> None:
        nonlocal buffer, buffer_chars, buffer_start, buffer_end
        if buffer and buffer_start is not None and buffer_end is not None:
            chunks.append((buffer_start, buffer_end, "\n\n".join(buffer)))
        buffer = []
        buffer_chars = 0
        buffer_start = None
        buffer_end = None

    for page_number, raw_text in pages:
        text = raw_text.strip()
        if not text:
            continue

        # A very long page is split on its own, with every piece mapped to
        # the same physical PDF page.
        if len(text) > max_chars:
            flush_buffer()
            for part in split_long_text(text, max_chars):
                chunks.append((page_number, page_number, part))
            continue

        extra_chars = len(text) + (2 if buffer else 0)
        if buffer and buffer_chars + extra_chars > max_chars:
            flush_buffer()

        if not buffer:
            buffer_start = page_number

        buffer.append(text)
        buffer_chars += len(text) + (2 if len(buffer) > 1 else 0)
        buffer_end = page_number

    flush_buffer()
    return chunks


# ---------------------------------------------------------------------------
# Step 1: populate document chunks
# ---------------------------------------------------------------------------

def populate_chunks() -> dict[str, int]:
    """Find PDFs recursively and store their chunks and source page ranges.

    PDF paths are stored relative to TARGET_PDF_DIR, using forward slashes.
    Existing unchanged files are skipped. Changed files have their old
    chunks replaced. This function does not store a separate full-text copy.
    """
    if not TARGET_PDF_DIR.is_dir():
        raise FileNotFoundError(f"PDF directory does not exist: {TARGET_PDF_DIR}")

    initialise_db()

    pdf_paths = sorted(
        (path for path in TARGET_PDF_DIR.rglob("*")
         if path.is_file() and path.suffix.lower() == ".pdf"),
        key=lambda path: path.as_posix().lower(),
    )

    stats = {"found": len(pdf_paths), "indexed": 0, "unchanged": 0, "failed": 0, "chunks": 0}

    for pdf_path in pdf_paths:
        relative_path = pdf_path.relative_to(TARGET_PDF_DIR).as_posix()

        try:
            file_hash = sha256_file(pdf_path)

            with open_db() as conn:
                existing = conn.execute(
                    "SELECT id, file_hash FROM documents WHERE relative_path = ?",
                    (relative_path,),
                ).fetchone()

            if existing and existing["file_hash"] == file_hash:
                stats["unchanged"] += 1
                continue

            # Extract and chunk before changing the database. If PDF reading
            # fails, the previous indexed version (if any) remains intact.
            pages = read_pdf_pages(pdf_path)
            chunks = make_chunks(pages)

            with open_db() as conn:
                with conn:
                    existing = conn.execute(
                        "SELECT id FROM documents WHERE relative_path = ?",
                        (relative_path,),
                    ).fetchone()

                    if existing:
                        document_id = int(existing["id"])
                        conn.execute(
                            "UPDATE documents SET file_hash = ? WHERE id = ?",
                            (file_hash, document_id),
                        )
                        conn.execute(
                            "DELETE FROM chunks WHERE document_id = ?",
                            (document_id,),
                        )
                    else:
                        cursor = conn.execute(
                            "INSERT INTO documents(relative_path, file_hash) VALUES (?, ?)",
                            (relative_path, file_hash),
                        )
                        document_id = int(cursor.lastrowid)

                    conn.executemany(
                        """
                        INSERT INTO chunks (
                            document_id, chunk_index, page_start, page_end, text
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        [
                            (document_id, index, page_start, page_end, chunk_text)
                            for index, (page_start, page_end, chunk_text) in enumerate(chunks)
                        ],
                    )

            stats["indexed"] += 1
            stats["chunks"] += len(chunks)
            print(f"Indexed: {relative_path} ({len(chunks)} chunks)")

        except Exception as exc:
            stats["failed"] += 1
            print(f"FAILED: {relative_path}: {exc}")

    print("\nChunk population finished:")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    return stats


# ---------------------------------------------------------------------------
# Step 2: populate embeddings
# ---------------------------------------------------------------------------

def normalise_vector(vector: np.ndarray) -> np.ndarray:
    """Return a finite, L2-normalised float32 vector."""
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    if not np.all(np.isfinite(vector)):
        raise ValueError("Embedding contains NaN or infinite values")

    norm = float(np.linalg.norm(vector))
    if norm == 0:
        raise ValueError("Embedding has zero length")

    return vector / norm


def populate_embeddings(
    embed_texts: EmbedTexts,
    model_name: str,
    batch_size: int = EMBEDDING_BATCH_SIZE,
) -> int:
    """Create embeddings for chunks that do not have one yet.

    `embed_texts` is supplied by you later. It must accept a list of strings
    and return a numeric array shaped (number_of_texts, embedding_dimension).

    If model_name changes, all old embeddings are cleared and recomputed.
    """
    initialise_db()

    with open_db() as conn:
        old_model_row = conn.execute(
            "SELECT value FROM settings WHERE key = 'embedding_model'"
        ).fetchone()
        old_model = old_model_row["value"] if old_model_row else None

        if old_model is not None and old_model != model_name:
            print(f"Embedding model changed: {old_model} -> {model_name}. Rebuilding vectors.")
            with conn:
                conn.execute("UPDATE chunks SET embedding = NULL")

        with conn:
            conn.execute(
                """
                INSERT INTO settings(key, value) VALUES ('embedding_model', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (model_name,),
            )

    total_embedded = 0

    while True:
        with open_db() as conn:
            rows = conn.execute(
                "SELECT id, text FROM chunks WHERE embedding IS NULL ORDER BY id LIMIT ?",
                (batch_size,),
            ).fetchall()

        if not rows:
            break

        ids = [int(row["id"]) for row in rows]
        texts = [str(row["text"]) for row in rows]

        vectors = np.asarray(embed_texts(texts), dtype=np.float32)
        if vectors.ndim != 2 or vectors.shape[0] != len(texts):
            raise ValueError(
                "embed_texts must return an array shaped "
                f"({len(texts)}, embedding_dimension); got {vectors.shape}"
            )
        if vectors.shape[1] == 0:
            raise ValueError("Embedding dimension cannot be zero")
        if not np.all(np.isfinite(vectors)):
            raise ValueError("Embeddings contain NaN or infinite values")

        # Normalise rows so a dot product later is cosine similarity.
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        if np.any(norms == 0):
            raise ValueError("One or more embeddings have zero length")
        vectors = vectors / norms
        vectors = np.asarray(vectors, dtype="<f4")

        with open_db() as conn:
            with conn:
                conn.executemany(
                    "UPDATE chunks SET embedding = ? WHERE id = ?",
                    [
                        (vectors[index].tobytes(), chunk_id)
                        for index, chunk_id in enumerate(ids)
                    ],
                )
                conn.execute(
                    """
                    INSERT INTO settings(key, value) VALUES ('embedding_dimension', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (str(vectors.shape[1]),),
                )

        total_embedded += len(rows)
        print(f"Embedded {total_embedded} chunks...")

    print(f"Embedding population finished: {total_embedded} chunks embedded.")
    return total_embedded


# ---------------------------------------------------------------------------
# Step 3: query text -> vector -> most similar chunks -> PDF path + pages
# ---------------------------------------------------------------------------

def find_similar(
    query: str,
    embed_texts: EmbedTexts,
    top_k: int = 5,
    batch_size: int = SEARCH_BATCH_SIZE,
) -> list[dict[str, object]]:
    """Return the most similar chunks, including their PDF path and pages.

    The same embedding model must be used here as in populate_embeddings().
    Similarity is cosine similarity because both stored and query vectors
    are L2-normalised.
    """
    if top_k < 1:
        return []

    query_vectors = np.asarray(embed_texts([query]), dtype=np.float32)
    if query_vectors.ndim != 2 or query_vectors.shape[0] != 1:
        raise ValueError("embed_texts([query]) must return an array shaped (1, D)")
    query_vector = normalise_vector(query_vectors[0])

    results: list[dict[str, object]] = []

    with open_db() as conn:
        cursor = conn.execute(
            """
            SELECT
                c.id,
                d.relative_path,
                c.page_start,
                c.page_end,
                c.text,
                c.embedding
            FROM chunks AS c
            JOIN documents AS d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL
            ORDER BY c.id
            """
        )

        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break

            vectors = []
            for row in rows:
                vector = np.frombuffer(row["embedding"], dtype="<f4")
                if vector.size != query_vector.size:
                    raise ValueError(
                        "Embedding dimension mismatch. Make sure the query and "
                        "stored chunks use the same embedding model."
                    )
                vectors.append(vector)

            matrix = np.vstack(vectors)
            scores = matrix @ query_vector

            for row, score in zip(rows, scores):
                results.append(
                    {
                        "chunk_id": int(row["id"]),
                        "path": str(row["relative_path"]),
                        "page_start": int(row["page_start"]),
                        "page_end": int(row["page_end"]),
                        "score": float(score),
                        "text": str(row["text"]),
                    }
                )

    results.sort(key=lambda item: float(item["score"]), reverse=True)
    return results[:top_k]


# ---------------------------------------------------------------------------
# SentenceTransformers adapter
# ---------------------------------------------------------------------------

def make_sentence_transformer_embedder(model_name: str) -> EmbedTexts:
    """Load a SentenceTransformer and return the embed_texts(texts) function.

    The model is loaded once and reused for all batches and queries.
    Import is local so the rest of this module can still be imported without
    sentence-transformers installed, as long as this helper is not called.
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "Install Sentence Transformers first: pip install sentence-transformers"
        ) from exc

    model = SentenceTransformer(model_name)

    def embed_texts(texts: list[str]) -> np.ndarray:
        return model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

    return embed_texts


# ---------------------------------------------------------------------------
# Run this file to populate chunks AND their embeddings.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    
    # 1. Find PDFs, extract page text, and create page-mapped chunks.
    populate_chunks()

    # 2. Create embeddings for chunks that do not have one yet.
    #    Existing embeddings are retained unless a PDF changed or the model changed.
    embed_texts = make_sentence_transformer_embedder(EMBEDDING_MODEL_NAME)
    populate_embeddings(embed_texts, model_name=EMBEDDING_MODEL_NAME)

    # 3. Optional interactive search.
    while True:
        query = input("\nSearch your PDFs (or type 'exit'): ").strip()
        if query.lower() in {"exit", "quit"}:
            break
        if not query:
            continue

        matches = find_similar(query, embed_texts, top_k=5)
        for match in matches:
            
            print(
                f"\nscore={match['score']:.4f}  "
                f"{match['path']}  "
                f"pages {match['page_start']}-{match['page_end']}"
            )
            print(match["text"][:1000])
