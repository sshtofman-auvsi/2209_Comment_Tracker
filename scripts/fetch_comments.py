"""
Fetch all public comments from regulations.gov for FAA-2026-4558.
Outputs docs/comments.json for the dashboard to consume.

Usage:
    REGULATIONS_GOV_API_KEY=your_key python scripts/fetch_comments.py
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

API_BASE = "https://api.regulations.gov/v4"
DOCKET_ID = "FAA-2026-4558"
DOCUMENT_ID = "FAA-2026-4558-0001"
PAGE_SIZE = 250
DELAY_BETWEEN_REQUESTS = 0.5  # seconds; registered key allows ~1000 req/hour

API_KEY = os.environ.get("REGULATIONS_GOV_API_KEY", "")
if not API_KEY:
    print("ERROR: REGULATIONS_GOV_API_KEY environment variable not set.", file=sys.stderr)
    sys.exit(1)

HEADERS = {"X-Api-Key": API_KEY}
OUT_FILE = Path(__file__).parent.parent / "docs" / "comments.json"


def get(url, params=None, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=30)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 60))
                print(f"  Rate limited — waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            print(f"  Request error ({e}), retrying in 5s...", file=sys.stderr)
            time.sleep(5)


def fetch_all_comment_ids():
    """Page through comment list and return all comment IDs."""
    ids = []
    page = 1
    while True:
        data = get(f"{API_BASE}/comments", {
            "filter[commentOnId]": DOCUMENT_ID,
            "page[size]": PAGE_SIZE,
            "page[number]": page,
            "sort": "postedDate",
        })
        batch = data.get("data", [])
        ids.extend(c["id"] for c in batch)
        meta = data.get("meta", {})
        total_pages = meta.get("totalPages", 1)
        print(f"  Page {page}/{total_pages} — {len(batch)} comments", file=sys.stderr)
        if page >= total_pages:
            break
        page += 1
        time.sleep(DELAY_BETWEEN_REQUESTS)
    return ids


def fetch_comment_detail(comment_id):
    """Fetch full detail for a single comment."""
    data = get(f"{API_BASE}/comments/{comment_id}")
    attrs = data.get("data", {}).get("attributes", {})

    text = (attrs.get("comment") or "").strip()
    has_attachment = text.lower().startswith("see attached") or not text

    return {
        "id": comment_id,
        "commenter": _name(attrs),
        "organization": attrs.get("organization") or "",
        "city": attrs.get("city") or "",
        "state_province": attrs.get("stateProvinceRegion") or "",
        "country": attrs.get("country") or "",
        "posted_date": attrs.get("postedDate") or "",
        "received_date": attrs.get("receiveDate") or "",
        "comment_text": text if not has_attachment else "",
        "has_attachment": has_attachment,
        "category": attrs.get("category") or "",
        "submitter_type": attrs.get("submitterType") or "",
        "url": f"https://www.regulations.gov/comment/{comment_id}",
    }


def _name(attrs):
    first = (attrs.get("firstName") or "").strip()
    last = (attrs.get("lastName") or "").strip()
    if first or last:
        return f"{first} {last}".strip()
    return attrs.get("title") or ""


def main():
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    print("Fetching comment IDs...", file=sys.stderr)
    ids = fetch_all_comment_ids()
    print(f"Total comments found: {len(ids)}", file=sys.stderr)

    # Load existing data so we only re-fetch new/missing comments
    existing = {}
    if OUT_FILE.exists():
        try:
            old = json.loads(OUT_FILE.read_text())
            existing = {c["id"]: c for c in old.get("comments", [])}
            print(f"Existing cached comments: {len(existing)}", file=sys.stderr)
        except Exception:
            pass

    comments = []
    new_count = 0
    for i, cid in enumerate(ids):
        if cid in existing:
            comments.append(existing[cid])
            continue
        try:
            detail = fetch_comment_detail(cid)
            comments.append(detail)
            new_count += 1
            print(f"  [{i+1}/{len(ids)}] {cid} — {detail['commenter'] or detail['organization'] or 'Anonymous'}", file=sys.stderr)
            time.sleep(DELAY_BETWEEN_REQUESTS)
        except Exception as e:
            print(f"  WARNING: failed to fetch {cid}: {e}", file=sys.stderr)

    print(f"Fetched {new_count} new comments.", file=sys.stderr)

    output = {
        "docket_id": DOCKET_ID,
        "document_id": DOCUMENT_ID,
        "title": "Restrict the Operation of Unmanned Aircraft in Close Proximity to a Fixed Site Facility",
        "comment_period_end": "2026-07-07",
        "total_comments": len(comments),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "comments": comments,
    }

    OUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"Wrote {len(comments)} comments to {OUT_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
