#!/usr/bin/env python3
"""Local web UI for the Al Islam library Chroma DB: semantic and word/sentence search.

    ./bin/python alislam_search_app.py            # then open http://127.0.0.1:8765
    ./bin/python alislam_search_app.py --port 9000

Semantic search embeds the query with gemini-embedding-2 (same model, size and prefix as
"Al Islam Library RAG.ipynb"), so it needs GOOGLE_API_KEY from the environment or .env.
Word/sentence search is exact substring matching in the stored pages and needs no API calls.
The server only listens on this computer (127.0.0.1).
"""
import argparse
import json
import os
import time
from pathlib import Path
from typing import List, Optional

import chromadb
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent
CHROMA_DIR = HERE / "chroma_db" / "alislam_library"
COLLECTION = "langchain"
CATALOG_PATH = HERE / "alislam_books_by_category.json"
DOWNLOAD_MANIFEST = HERE / "alislam_books_txt" / "_download_manifest.json"
EMBED_MANIFEST = CHROMA_DIR / "_embedded_books.json"
UI_FILE = HERE / "alislam_search_ui.html"

EMBED_MODEL = "gemini-embedding-2"
EMBED_DIM = 3072
QUERY_PREFIX = "task: search result | query: {text}"


def load_api_key():
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    env_file = HERE / ".env"
    if not key and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() in ("GOOGLE_API_KEY", "GEMINI_API_KEY") and value.strip():
                key = value.strip().strip("'\"")
                break
    return key


collection = chromadb.PersistentClient(path=str(CHROMA_DIR)).get_collection(COLLECTION)
_genai_client = None


def embed_query(text):
    global _genai_client
    from google import genai
    from google.genai import errors, types

    if _genai_client is None:
        key = load_api_key()
        if not key:
            raise HTTPException(500, "No GOOGLE_API_KEY in the environment or .env, so semantic search is off.")
        _genai_client = genai.Client(api_key=key)
    for attempt in range(4):
        try:
            result = _genai_client.models.embed_content(
                model=EMBED_MODEL,
                contents=[types.Content(parts=[types.Part.from_text(text=QUERY_PREFIX.format(text=text))])],
                config=types.EmbedContentConfig(output_dimensionality=EMBED_DIM),
            )
            return result.embeddings[0].values
        except errors.APIError as exc:
            code = getattr(exc, "code", None)
            if code == 429 or (code or 0) >= 500:
                time.sleep(2 * (attempt + 1))
                continue
            raise HTTPException(502, f"Gemini refused the query ({code}): {str(exc)[:200]}")
    raise HTTPException(503, "Gemini is rate-limiting; try again in a minute.")


def book_list():
    """Embedded books with their name, category and language, for the filters."""
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    info = {bid: dict(b, category=cat) for cat, books in catalog.items() for bid, b in books.items()}
    embedded = json.loads(EMBED_MANIFEST.read_text(encoding="utf-8")) if EMBED_MANIFEST.exists() else {}
    manifest = json.loads(DOWNLOAD_MANIFEST.read_text(encoding="utf-8")) if DOWNLOAD_MANIFEST.exists() else {}
    books = []
    for bid, e in embedded.items():
        if not e.get("pages"):
            continue
        b = info.get(bid, {})
        books.append({
            "id": bid,
            "name": manifest.get(bid, {}).get("name") or b.get("name") or bid,
            "category": b.get("category") or manifest.get(bid, {}).get("category", ""),
            "language": b.get("language", ""),
            "pages": e["pages"],
        })
    books.sort(key=lambda b: b["name"].lower())
    return books


BOOKS = book_list()


def build_where(category=None, book_ids=None, language=None):
    filters = []
    if category:
        filters.append({"category": category})
    if book_ids:
        filters.append({"book_id": {"$in": list(book_ids)}})
    if language:
        filters.append({"language": language})
    if not filters:
        return None
    return filters[0] if len(filters) == 1 else {"$and": filters}


def to_hit(doc, meta, score=None):
    return {
        "book": meta.get("book"),
        "book_id": meta.get("book_id"),
        "category": meta.get("category"),
        "language": meta.get("language"),
        "page": meta.get("page"),
        "page_index": meta.get("page_index"),
        "source": meta.get("source"),
        "text": doc,
        "score": score,
    }


class Filters(BaseModel):
    query: str
    category: Optional[str] = None
    book_ids: Optional[List[str]] = None
    language: Optional[str] = None


class SemanticRequest(Filters):
    k: int = Field(20, ge=1, le=200)


class LexicalRequest(Filters):
    mode: str = "sentence"
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)


app = FastAPI(title="Al Islam library search")


@app.get("/")
def index():
    return FileResponse(UI_FILE, media_type="text/html")


@app.get("/api/meta")
def meta():
    categories = {}
    languages = {}
    for b in BOOKS:
        categories[b["category"]] = categories.get(b["category"], 0) + b["pages"]
        if b["language"]:
            languages[b["language"]] = languages.get(b["language"], 0) + b["pages"]
    return {
        "pages": collection.count(),
        "books": BOOKS,
        "categories": [{"name": n, "pages": p} for n, p in sorted(categories.items(), key=lambda kv: kv[0].lower())],
        "languages": [{"code": c, "pages": p} for c, p in sorted(languages.items(), key=lambda kv: -kv[1])],
        "semantic_available": bool(load_api_key()),
    }


@app.post("/api/semantic")
def semantic(req: SemanticRequest):
    query = req.query.strip()
    if not query:
        return {"hits": [], "seconds": 0}
    started = time.monotonic()
    vector = embed_query(query)
    result = collection.query(
        query_embeddings=[vector],
        n_results=req.k,
        where=build_where(req.category, req.book_ids, req.language),
        include=["documents", "metadatas", "distances"],
    )
    hits = [to_hit(d, m, round(1 - dist, 4))
            for d, m, dist in zip(result["documents"][0], result["metadatas"][0], result["distances"][0])]
    return {"hits": hits, "seconds": round(time.monotonic() - started, 2)}


@app.post("/api/lexical")
def lexical(req: LexicalRequest):
    query = req.query.strip()
    if not query:
        return {"hits": [], "seconds": 0, "more": False}
    if req.mode == "sentence":
        where_document = {"$contains": query}
    elif req.mode == "word":
        tokens = query.split()
        where_document = ({"$contains": tokens[0]} if len(tokens) == 1
                          else {"$and": [{"$contains": t} for t in tokens]})
    else:
        raise HTTPException(400, "mode must be 'sentence' or 'word'")
    started = time.monotonic()
    # Ask for one extra row to know whether a "load more" button is needed.
    result = collection.get(
        where=build_where(req.category, req.book_ids, req.language),
        where_document=where_document,
        limit=req.limit + 1,
        offset=req.offset,
        include=["documents", "metadatas"],
    )
    rows = list(zip(result["documents"], result["metadatas"]))
    more = len(rows) > req.limit
    hits = [to_hit(d, m) for d, m in rows[:req.limit]]
    return {"hits": hits, "seconds": round(time.monotonic() - started, 2), "more": more}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    print(f"{collection.count()} pages, {len(BOOKS)} books. Open http://127.0.0.1:{args.port}")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
