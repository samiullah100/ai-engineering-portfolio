#!/usr/bin/env python3
"""Catalogue every book in the Al Islam library (https://new.alislam.org/library).

For each book it records the id used by the text API in
"Rohani khazain books in txt.ipynb" (/api/books/text?id=...&pages=N), the
name, and the first and last page, grouped by category.

    python3 alislam_book_catalog.py

Writes:
  alislam_books_by_category.json  {category: {book_id: {name, start_page, end_page, ...}}}
                                  Each category can be pasted as the notebook's `books`.
                                  Categories are library collections; books in no collection
                                  are grouped as "Topic: <first topic>" or "Uncategorized".
                                  range_estimated=true: the page gave only a page count.
  alislam_books.csv               the same rows as one table.

Only the public book pages listed in the library sitemap are read; /api/ is
disallowed by robots.txt and is not used. Requests are spaced one second apart
(the robots.txt crawl-delay). Results are cached, so a rerun resumes.
"""
import csv
import json
import re
import sys
import time
from pathlib import Path

import requests

BASE = "https://new.alislam.org/library/"
HERE = Path(__file__).resolve().parent
CACHE = HERE / "alislam_book_catalog_cache.json"
OUT_JSON = HERE / "alislam_books_by_category.json"
OUT_CSV = HERE / "alislam_books.csv"
DELAY = 1.0

session = requests.Session()
session.headers["User-Agent"] = "Mozilla/5.0 (compatible; personal-catalogue-script)"
last_request = 0.0


def get(url):
    global last_request
    for attempt in range(4):
        wait = DELAY - (time.monotonic() - last_request)
        if wait > 0:
            time.sleep(wait)
        last_request = time.monotonic()
        try:
            response = session.get(url, timeout=90)
        except requests.RequestException as exc:
            print("  network error (%s), retrying: %s" % (type(exc).__name__, url), flush=True)
            time.sleep(10 * (attempt + 1))
            continue
        # This site also answers missing pages with 500, so retry those only once.
        if response.status_code == 429 or (response.status_code >= 500 and attempt == 0):
            print("  HTTP %s, retrying: %s" % (response.status_code, url), flush=True)
            time.sleep(20 if response.status_code == 429 else 5)
            continue
        response.encoding = "utf-8"
        return response
    return None


def flight_data(html):
    """Join the Next.js data chunks embedded in the page into one string."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', html)
    return "".join(json.loads('"' + chunk + '"') for chunk in chunks)


def json_object_after(text, key):
    index = text.find('"%s":{' % key)
    if index < 0:
        return None
    return json.JSONDecoder().raw_decode(text, index + len(key) + 3)[0]


def collection_names(sitemap_text):
    """Map collection ids to titles, from the collections index and each collection page."""
    pages = [BASE + "en/collections"]
    pages += sorted(set(re.findall(r"<loc>\s*(https://new\.alislam\.org/library/collections/[^<\s]+)\s*</loc>", sitemap_text)))
    names = {}
    for page in pages:
        response = get(page)
        if response is None or response.status_code != 200:
            continue
        data = flight_data(response.text)
        for cid, title in re.findall(r'\{"id":"([a-z0-9][^"$]*)","title":(\{[^{}]*\})', data):
            try:
                title = json.loads(title)
            except ValueError:
                continue
            if title.get("en") or title.get("ur"):
                names.setdefault(cid, title.get("en") or title.get("ur"))
    return names


def book_record(url):
    response = get(url)
    if response is None:
        return {"error": "request failed"}
    if response.status_code != 200:
        return {"error": "HTTP %d" % response.status_code}
    info = json_object_after(flight_data(response.text), "bookInfo")
    if not info:
        return {"error": "no bookInfo on page"}
    pages = info.get("pageInfo") or {}
    title = info.get("title") or {}
    return {
        "book_id": info.get("id", ""),
        "slug": info.get("slug", ""),
        "name": title.get("en") or title.get("ur") or info.get("slug", ""),
        "name_ur": title.get("ur", ""),
        "start_page": pages.get("startPage"),
        "end_page": pages.get("endPage"),
        "volume_pages": pages.get("numberOfPages"),
        "language": info.get("language", ""),
        "collection_id": info.get("collectionId", ""),
        "volume_id": info.get("bundleId", ""),
        "type": (info.get("meta") or {}).get("type", ""),
        "topics": [t.get("name", "") for t in info.get("topics") or []],
        "has_text": info.get("hasText"),
        "url": response.url,
    }


def main():
    sitemap = get(BASE + "sitemap.xml")
    if sitemap is None or sitemap.status_code != 200:
        sys.exit("Could not read the library sitemap.")
    urls = sorted(set(re.findall(r"<loc>\s*(https://new\.alislam\.org/library/books/[^/<]+/info)\s*</loc>", sitemap.text)))
    print("%d books in the sitemap" % len(urls), flush=True)

    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    todo = [u for u in urls if u not in cache or "error" in cache[u]]
    print("%d to fetch (about %d minutes)" % (len(todo), len(todo) * 1.5 / 60 + 1), flush=True)
    for i, url in enumerate(todo, 1):
        cache[url] = book_record(url)
        if i % 25 == 0 or i == len(todo):
            CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            print("  %d/%d" % (i, len(todo)), flush=True)

    names = collection_names(sitemap.text)
    books, errors = {}, []
    for url in urls:
        record = cache[url]
        if "error" in record:
            errors.append((url, record["error"]))
            continue
        # Several slugs (e.g. /lujja-tun-noor-urdu and /rk-...) can point to one book id.
        books.setdefault(record["book_id"] or record["slug"], record)

    grouped = {}
    for book_id, r in sorted(books.items(), key=lambda kv: kv[1]["name"].lower()):
        cid = r["collection_id"]
        if not cid:
            # Books outside any collection are grouped by their first topic instead.
            category = ("Topic: " + r["topics"][0]) if r["topics"] else "Uncategorized"
        else:
            category = names.get(cid) or cid.replace("-", " ").title()
            if cid.endswith("-en"):
                # e.g. ruhani-khazain and ruhani-khazain-en share the title "Ruhani Khazain".
                category += " (English)"
        r["category"] = category
        # Standalone books that do list a range use 0..numberOfPages (1,083 of 1,084),
        # so books that only give numberOfPages get that range, marked as estimated.
        estimated = r["start_page"] is None and r["volume_pages"] is not None and not r["volume_id"]
        start = 0 if estimated else r["start_page"]
        end = r["volume_pages"] if estimated else r["end_page"]
        grouped.setdefault(category, {})[book_id] = {
            "name": r["name"],
            "start_page": start,
            "end_page": end,
            "range_estimated": estimated,
            "name_ur": r["name_ur"],
            "language": r["language"],
            "volume_id": r["volume_id"],
            "volume_pages": r["volume_pages"],
            "topics": r["topics"],
            "url": r["url"],
        }
    # Collections first, then topics, then uncategorised books.
    grouped = dict(sorted(grouped.items(), key=lambda kv: (kv[0].startswith("Topic: "), kv[0] == "Uncategorized", kv[0].lower())))
    OUT_JSON.write_text(json.dumps(grouped, ensure_ascii=False, indent=2), encoding="utf-8")

    columns = ["category", "book_id", "name", "start_page", "end_page", "range_estimated", "name_ur", "language",
               "volume_id", "volume_pages", "topics", "url"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, columns, extrasaction="ignore")
        writer.writeheader()
        for category, items in grouped.items():
            for book_id, r in items.items():
                writer.writerow(dict(r, category=category, book_id=book_id, topics="; ".join(r["topics"])))

    rows = [r for items in grouped.values() for r in items.values()]
    missing = sum(1 for r in rows if r["start_page"] is None or r["end_page"] is None)
    print("Ranges estimated from the page count: %d" % sum(r["range_estimated"] for r in rows))
    print("Saved %d books in %d categories to %s and %s" % (len(books), len(grouped), OUT_JSON.name, OUT_CSV.name))
    print("Books without a start/end page: %d; pages that failed: %d" % (missing, len(errors)))
    for url, error in errors[:20]:
        print("  FAILED %s: %s" % (url, error))


if __name__ == "__main__":
    main()
