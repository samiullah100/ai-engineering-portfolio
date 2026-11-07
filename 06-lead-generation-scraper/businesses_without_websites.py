#!/usr/bin/env python3
"""
Extract Canadian businesses that appear to have no website.

Primary source: Yellow Pages Canada (no API key required).
Optional source: Google Places API — requires a separate Maps Platform key
(set GOOGLE_PLACES_API_KEY; a Gemini API key will not work).

Usage:
  python canada_businesses_no_website.py --demo
  python canada_businesses_no_website.py --source yp
  python canada_businesses_no_website.py --source google
  python canada_businesses_no_website.py --resume
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

USER_AGENT = "canada-business-extractor/1.0 (research; contact: local)"
REQUEST_DELAY_SEC = 1.2
MAX_YP_PAGES = 50  # Yellow Pages caps results around page 50

DEFAULT_OUTPUT = Path("canada_businesses_no_website.csv")
DEFAULT_CHECKPOINT = Path("canada_businesses_no_website_checkpoint.json")

# Major cities/towns across all provinces & territories (Yellow Pages "City+PP" format).
CANADIAN_LOCATIONS: list[tuple[str, str]] = [
    # Alberta
    ("Calgary", "AB"), ("Edmonton", "AB"), ("Red Deer", "AB"), ("Lethbridge", "AB"),
    ("Medicine Hat", "AB"), ("Grande Prairie", "AB"), ("Airdrie", "AB"), ("Spruce Grove", "AB"),
    ("Leduc", "AB"), ("Fort McMurray", "AB"), ("Lloydminster", "AB"), ("Camrose", "AB"),
    # British Columbia
    ("Vancouver", "BC"), ("Victoria", "BC"), ("Surrey", "BC"), ("Burnaby", "BC"),
    ("Richmond", "BC"), ("Kelowna", "BC"), ("Abbotsford", "BC"), ("Coquitlam", "BC"),
    ("Langley", "BC"), ("Nanaimo", "BC"), ("Kamloops", "BC"), ("Chilliwack", "BC"),
    ("Prince George", "BC"), ("Vernon", "BC"), ("Courtenay", "BC"), ("Penticton", "BC"),
    # Manitoba
    ("Winnipeg", "MB"), ("Brandon", "MB"), ("Steinbach", "MB"), ("Thompson", "MB"),
    ("Portage la Prairie", "MB"), ("Winkler", "MB"),
    # New Brunswick
    ("Moncton", "NB"), ("Saint John", "NB"), ("Fredericton", "NB"), ("Dieppe", "NB"),
    ("Miramichi", "NB"), ("Edmundston", "NB"),
    # Newfoundland and Labrador
    ("St. John's", "NL"), ("Corner Brook", "NL"), ("Grand Falls-Windsor", "NL"),
    ("Gander", "NL"), ("Mount Pearl", "NL"),
    # Nova Scotia
    ("Halifax", "NS"), ("Dartmouth", "NS"), ("Sydney", "NS"), ("Truro", "NS"),
    ("New Glasgow", "NS"), ("Glace Bay", "NS"),
    # Northwest Territories
    ("Yellowknife", "NT"), ("Hay River", "NT"), ("Inuvik", "NT"),
    # Nunavut
    ("Iqaluit", "NU"), ("Rankin Inlet", "NU"),
    # Ontario
    ("Toronto", "ON"), ("Ottawa", "ON"), ("Mississauga", "ON"), ("Brampton", "ON"),
    ("Hamilton", "ON"), ("London", "ON"), ("Markham", "ON"), ("Vaughan", "ON"),
    ("Kitchener", "ON"), ("Windsor", "ON"), ("Richmond Hill", "ON"), ("Oakville", "ON"),
    ("Burlington", "ON"), ("Greater Sudbury", "ON"), ("Oshawa", "ON"), ("Barrie", "ON"),
    ("St. Catharines", "ON"), ("Cambridge", "ON"), ("Kingston", "ON"), ("Guelph", "ON"),
    ("Thunder Bay", "ON"), ("Waterloo", "ON"), ("Brantford", "ON"), ("Pickering", "ON"),
    ("Niagara Falls", "ON"), ("Peterborough", "ON"), ("Sarnia", "ON"), ("North Bay", "ON"),
    ("Belleville", "ON"), ("Cornwall", "ON"), ("Chatham", "ON"), ("Orillia", "ON"),
    # Prince Edward Island
    ("Charlottetown", "PE"), ("Summerside", "PE"), ("Stratford", "PE"),
    # Quebec
    ("Montreal", "QC"), ("Quebec City", "QC"), ("Laval", "QC"), ("Gatineau", "QC"),
    ("Longueuil", "QC"), ("Sherbrooke", "QC"), ("Saguenay", "QC"), ("Levis", "QC"),
    ("Trois-Rivieres", "QC"), ("Terrebonne", "QC"), ("Saint-Jean-sur-Richelieu", "QC"),
    ("Repentigny", "QC"), ("Brossard", "QC"), ("Drummondville", "QC"), ("Granby", "QC"),
    ("Blainville", "QC"), ("Saint-Hyacinthe", "QC"), ("Rimouski", "QC"), ("Victoriaville", "QC"),
    # Saskatchewan
    ("Saskatoon", "SK"), ("Regina", "SK"), ("Prince Albert", "SK"), ("Moose Jaw", "SK"),
    ("Swift Current", "SK"), ("Yorkton", "SK"),
    # Yukon
    ("Whitehorse", "YT"), ("Dawson City", "YT"),
]

# Broad category coverage for local businesses on Yellow Pages.
BUSINESS_CATEGORIES: list[str] = [
    "Restaurants", "Dentists", "Medical Clinics", "Car Repair", "Grocery Stores",
    "Plumbers", "Electricians", "Lawyers", "Accountants", "Hair Salons",
    "Auto Repair", "Pharmacies", "Real Estate Agents", "Insurance", "Banks",
    "Hotels", "Motels", "Contractors", "Roofing", "HVAC",
    "Landscaping", "Pest Control", "Locksmiths", "Moving Companies", "Storage",
    "Florists", "Bakeries", "Butcher Shops", "Coffee Shops", "Bars",
    "Gyms", "Yoga Studios", "Spas", "Nail Salons", "Barbers",
    "Veterinarians", "Pet Stores", "Daycare", "Tutoring", "Driving Schools",
    "Optometrists", "Chiropractors", "Physiotherapists", "Massage Therapy",
    "Dry Cleaners", "Tailors", "Shoe Repair", "Furniture Stores", "Appliance Repair",
    "Computer Repair", "Printing Services", "Photographers", "Wedding Planners",
    "Caterers", "Event Planners", "Cleaners", "Janitorial Services", "Security Services",
    "Taxi Services", "Trucking", "Auto Body Repair", "Tire Dealers", "Car Dealers",
    "Hardware Stores", "Paint Stores", "Flooring", "Window Installation", "Garage Doors",
    "Pool Services", "Tree Service", "Excavating", "Concrete Contractors", "Masonry",
    "Welding", "Machine Shops", "Welding Supply", "Industrial Supply", "Office Supplies",
    "Bookstores", "Toy Stores", "Sporting Goods", "Bicycle Shops", "Jewelry Stores",
    "Pawn Shops", "Thrift Stores", "Antique Stores", "Gift Shops", "Art Galleries",
    "Music Stores", "Video Stores", "Electronics Stores", "Cell Phone Stores",
    "Travel Agencies", "Employment Agencies", "Staffing Agencies", "Marketing Agencies",
    "Web Design", "Graphic Design", "Architects", "Engineers", "Surveyors",
    "Notaries", "Tax Services", "Financial Planners", "Mortgage Brokers", "Collection Agencies",
    "Funeral Homes", "Churches", "Schools", "Colleges", "Libraries",
    "Auto Parts", "Boat Dealers", "RV Dealers", "Motorcycle Dealers", "Trailer Dealers",
    "Paving", "Fencing", "Siding", "Insulation", "Solar Energy",
    "Waterproofing", "Foundation Repair", "Septic Services", "Well Drilling", "Irrigation",
]

DEMO_LOCATIONS = CANADIAN_LOCATIONS[:3]
DEMO_CATEGORIES = BUSINESS_CATEGORIES[:5]

SOCIAL_DOMAINS = (
    "facebook.com", "instagram.com", "twitter.com", "x.com", "linkedin.com",
    "youtube.com", "tiktok.com", "yelp.", "tripadvisor.", "google.com/maps",
)

CSV_FIELDS = [
    "business_name", "phone", "address", "city", "province", "category",
    "source", "listing_id", "yp_url", "google_maps_url", "scraped_at",
]


@dataclass
class BusinessRecord:
    business_name: str
    phone: str = ""
    address: str = ""
    city: str = ""
    province: str = ""
    category: str = ""
    source: str = ""
    listing_id: str = ""
    yp_url: str = ""
    google_maps_url: str = ""
    scraped_at: str = ""


@dataclass
class Checkpoint:
    completed_tasks: set[str] = field(default_factory=set)
    seen_ids: set[str] = field(default_factory=set)

    @staticmethod
    def load(path: Path) -> "Checkpoint":
        if not path.exists():
            return Checkpoint()
        data = json.loads(path.read_text(encoding="utf-8"))
        return Checkpoint(
            completed_tasks=set(data.get("completed_tasks", [])),
            seen_ids=set(data.get("seen_ids", [])),
        )

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "completed_tasks": sorted(self.completed_tasks),
                    "seen_ids": sorted(self.seen_ids),
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def yp_location_slug(city: str, province: str) -> str:
    return f"{city.replace(' ', '+')}+{province}"


def task_key(source: str, category: str, city: str, province: str) -> str:
    return f"{source}|{category}|{city}|{province}"


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def normalize_name(name: str) -> str:
    return re.sub(r"^\d+", "", name).strip()


def has_website_link(card: BeautifulSoup) -> bool:
    for anchor in card.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href.startswith("http"):
            continue
        lower = href.lower()
        if "yellowpages.ca" in lower or "yp.ca" in lower:
            continue
        if any(domain in lower for domain in SOCIAL_DOMAINS):
            continue
        return True
    return bool(card.select_one("a.listing__link--website, .listing__website"))


def parse_yp_card(card, category: str, city: str, province: str) -> BusinessRecord | None:
    name_el = card.select_one("h3, .listing__name, [itemprop=name]")
    if not name_el:
        return None
    name = normalize_name(name_el.get_text(strip=True))
    if not name:
        return None

    listing_id = ""
    analytics_el = card.select_one("[data-listinganalytics]")
    if analytics_el and analytics_el.get("data-listinganalytics"):
        try:
            listing_id = json.loads(analytics_el["data-listinganalytics"]).get("lk_listing_id", "")
        except json.JSONDecodeError:
            pass

    phone = ""
    phone_el = card.select_one(".mlr__item--phone, [itemprop=telephone]")
    if phone_el:
        phone = re.sub(r"^Phone Number", "", phone_el.get_text(strip=True)).strip()

    address = ""
    addr_el = card.select_one(".listing__address, [itemprop=address]")
    if addr_el:
        address = addr_el.get_text(" ", strip=True)

    yp_url = ""
    merchant_el = card.select_one("[data-merchanturl]")
    if merchant_el and merchant_el.get("data-merchanturl"):
        yp_url = "https://www.yellowpages.ca" + merchant_el["data-merchanturl"].split("?")[0]

    return BusinessRecord(
        business_name=name,
        phone=phone,
        address=address,
        city=city,
        province=province,
        category=category,
        source="yellowpages",
        listing_id=str(listing_id),
        yp_url=yp_url,
        scraped_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


def scrape_yp_search_page(
    http: requests.Session,
    category: str,
    city: str,
    province: str,
    page: int,
) -> tuple[list[BusinessRecord], int]:
    location = yp_location_slug(city, province)
    url = f"https://www.yellowpages.ca/search/si/{page}/{quote(category, safe='')}/{quote(location, safe='+')}"
    response = http.get(url, timeout=45)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    cards = soup.select(".listing__content")
    records: list[BusinessRecord] = []
    for card in cards:
        if has_website_link(card):
            continue
        record = parse_yp_card(card, category, city, province)
        if record:
            records.append(record)
    return records, len(cards)


def scrape_yp_task(
    http: requests.Session,
    category: str,
    city: str,
    province: str,
    max_pages: int,
) -> list[BusinessRecord]:
    all_records: list[BusinessRecord] = []
    for page in range(1, max_pages + 1):
        try:
            records, card_count = scrape_yp_search_page(http, category, city, province, page)
        except requests.RequestException as exc:
            print(f"  ! Request failed page {page}: {exc}", file=sys.stderr, flush=True)
            break
        if card_count == 0:
            break
        all_records.extend(records)
        time.sleep(REQUEST_DELAY_SEC)
    return all_records


def google_text_search(
    http: requests.Session,
    api_key: str,
    query: str,
) -> list[dict]:
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.nationalPhoneNumber,places.websiteUri,places.primaryType,"
            "places.googleMapsUri,nextPageToken"
        ),
    }
    results: list[dict] = []
    page_token: str | None = None
    while True:
        body: dict = {
            "textQuery": query,
            "regionCode": "CA",
            "pageSize": 20,
        }
        if page_token:
            body["pageToken"] = page_token
        response = http.post(url, headers=headers, json=body, timeout=45)
        response.raise_for_status()
        payload = response.json()
        results.extend(payload.get("places", []))
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
        time.sleep(REQUEST_DELAY_SEC)
    return results


def scrape_google_task(
    http: requests.Session,
    api_key: str,
    category: str,
    city: str,
    province: str,
) -> list[BusinessRecord]:
    query = f"{category} in {city}, {province}, Canada"
    places = google_text_search(http, api_key, query)
    records: list[BusinessRecord] = []
    for place in places:
        if place.get("websiteUri"):
            continue
        name = (place.get("displayName") or {}).get("text", "").strip()
        if not name:
            continue
        records.append(
            BusinessRecord(
                business_name=name,
                phone=place.get("nationalPhoneNumber", "") or "",
                address=place.get("formattedAddress", "") or "",
                city=city,
                province=province,
                category=category,
                source="google_places",
                listing_id=place.get("id", "") or "",
                google_maps_url=place.get("googleMapsUri", "") or "",
                scraped_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            )
        )
    return records


def dedupe_key(record: BusinessRecord) -> str:
    if record.listing_id:
        return f"{record.source}:{record.listing_id}"
    normalized_phone = re.sub(r"\D", "", record.phone)
    if normalized_phone:
        return f"phone:{normalized_phone}"
    return f"name:{record.business_name.lower()}|{record.city.lower()}|{record.province.lower()}"


def append_records(output_path: Path, records: Iterable[BusinessRecord]) -> int:
    write_header = not output_path.exists() or output_path.stat().st_size == 0
    count = 0
    with output_path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))
            count += 1
    return count


def run_extraction(
    source: str,
    locations: list[tuple[str, str]],
    categories: list[str],
    output_path: Path,
    checkpoint_path: Path,
    resume: bool,
    api_key: str | None,
    max_pages: int,
) -> None:
    checkpoint = Checkpoint.load(checkpoint_path) if resume else Checkpoint()
    http = session()
    total_new = 0
    tasks = len(locations) * len(categories)
    task_num = 0

    for city, province in locations:
        for category in categories:
            task_num += 1
            key = task_key(source, category, city, province)
            if key in checkpoint.completed_tasks:
                continue

            print(f"[{task_num}/{tasks}] {source} | {category} | {city}, {province}", flush=True)
            try:
                if source == "yp":
                    records = scrape_yp_task(http, category, city, province, max_pages)
                elif source == "google":
                    if not api_key:
                        raise RuntimeError("GOOGLE_PLACES_API_KEY is not set.")
                    records = scrape_google_task(http, api_key, category, city, province)
                else:
                    raise ValueError(f"Unknown source: {source}")
            except Exception as exc:
                print(f"  ! Skipping task after error: {exc}", file=sys.stderr)
                checkpoint.save(checkpoint_path)
                time.sleep(REQUEST_DELAY_SEC * 2)
                continue

            new_records: list[BusinessRecord] = []
            for record in records:
                dedupe = dedupe_key(record)
                if dedupe in checkpoint.seen_ids:
                    continue
                checkpoint.seen_ids.add(dedupe)
                new_records.append(record)

            added = append_records(output_path, new_records)
            total_new += added
            checkpoint.completed_tasks.add(key)
            checkpoint.save(checkpoint_path)
            print(
                f"  + {added} new records (task found {len(records)}, total new this run: {total_new})",
                flush=True,
            )
            time.sleep(REQUEST_DELAY_SEC)

    print(f"\nDone. Added {total_new} records -> {output_path.resolve()}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract Canadian businesses without a website to CSV."
    )
    parser.add_argument(
        "--source",
        choices=["yp", "google", "both"],
        default="yp",
        help="Data source: yellowpages (default), google places, or both",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output CSV path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=DEFAULT_CHECKPOINT,
        help=f"Checkpoint JSON for resume (default: {DEFAULT_CHECKPOINT})",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Quick run: first 3 cities x 5 categories only",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint file",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=MAX_YP_PAGES,
        help=f"Max Yellow Pages pages per city/category (default: {MAX_YP_PAGES}, hard cap ~50)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=REQUEST_DELAY_SEC,
        help=f"Delay between requests in seconds (default: {REQUEST_DELAY_SEC})",
    )
    return parser.parse_args()


def load_google_api_key() -> str | None:
    # Use a dedicated Maps Platform key only. Do not reuse Gemini keys from Business.ipynb.
    return os.environ.get("GOOGLE_PLACES_API_KEY")


def verify_google_places_api(http: requests.Session, api_key: str) -> None:
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName",
    }
    response = http.post(
        url,
        headers=headers,
        json={"textQuery": "business in Toronto Canada", "regionCode": "CA", "pageSize": 1},
        timeout=30,
    )
    if response.status_code == 200:
        return
    try:
        payload = response.json()
        message = payload.get("error", {}).get("message", response.text)
        reason = ""
        for detail in payload.get("error", {}).get("details", []):
            if detail.get("reason"):
                reason = detail["reason"]
                break
    except ValueError:
        message = response.text
        reason = ""

    extra = ""
    if reason == "API_KEY_SERVICE_BLOCKED":
        extra = (
            " This is often a Gemini key or a restricted Maps key. Create a separate "
            "Google Cloud API key with Places API (New) enabled (Maps Platform billing required)."
        )
    elif "not been used in project" in message or "disabled" in message.lower():
        extra = (
            " Enable 'Places API (New)' (not the legacy Places API) at "
            "https://console.cloud.google.com/apis/library/places.googleapis.com"
        )

    raise RuntimeError(
        "Google Places API check failed."
        + extra
        + f" Details: {message}"
    )


def main() -> None:
    args = parse_args()
    global REQUEST_DELAY_SEC
    REQUEST_DELAY_SEC = args.delay

    locations = DEMO_LOCATIONS if args.demo else CANADIAN_LOCATIONS
    categories = DEMO_CATEGORIES if args.demo else BUSINESS_CATEGORIES
    api_key = load_google_api_key()

    sources = ["yp", "google"] if args.source == "both" else [args.source]

    print(
        f"Starting extraction: {len(locations)} cities x {len(categories)} categories "
        f"x {len(sources)} source(s)"
    )
    if args.demo:
        print("Demo mode enabled.")

    if api_key and any(source in ("google", "both") for source in sources):
        try:
            verify_google_places_api(session(), api_key)
            print("Google Places API key verified.")
        except RuntimeError as exc:
            print(f"Warning: {exc}", file=sys.stderr)
            if args.source == "google":
                sys.exit(1)
            sources = [source for source in sources if source != "google"]

    for source in sources:
        if source == "google" and not api_key:
            print(
                "Warning: GOOGLE_PLACES_API_KEY not set. "
                "Use a Maps Platform key (not your Gemini key from Business.ipynb).",
                file=sys.stderr,
            )
            continue
        run_extraction(
            source=source,
            locations=locations,
            categories=categories,
            output_path=args.output,
            checkpoint_path=args.checkpoint,
            resume=args.resume,
            api_key=api_key,
            max_pages=args.max_pages,
        )


if __name__ == "__main__":
    main()
