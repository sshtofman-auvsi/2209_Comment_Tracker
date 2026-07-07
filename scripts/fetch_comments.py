"""
Fetch all public comments from regulations.gov for FAA-2026-4558.
For attachment-only comments, downloads the PDF and extracts text via pdfplumber.
Outputs docs/comments.json for the dashboard to consume.

Usage:
    REGULATIONS_GOV_API_KEY=your_key python scripts/fetch_comments.py
"""

import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import re
import requests

try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    print("WARNING: pdfplumber not installed — PDF text extraction disabled. Run: pip install pdfplumber", file=sys.stderr)

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
DATA_JS  = Path(__file__).parent.parent / "docs" / "data.js"


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
            "filter[docketId]": DOCKET_ID,
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


def fetch_pdf_urls(comment_id, raw_data):
    """Return list of PDF download URLs attached to a comment, if any."""
    urls = []
    try:
        included = raw_data.get("included") or []
        for item in included:
            if item.get("type") != "attachments":
                continue
            for fmt in (item.get("attributes", {}).get("fileFormats") or []):
                if isinstance(fmt, dict):
                    file_url = fmt.get("fileUrl", "")
                    if fmt.get("format", "").lower() == "pdf" or file_url.lower().endswith(".pdf"):
                        urls.append(file_url)
    except Exception as e:
        print(f"    WARNING: error parsing attachment URLs for {comment_id}: {e}", file=sys.stderr)
    return urls


PDF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/pdf,*/*",
}


def extract_pdf_text(pdf_url, comment_id=""):
    """Download a PDF and extract its text. Returns (text, scanned_flag)."""
    if not PDF_SUPPORT:
        return "", False
    try:
        headers = {**PDF_HEADERS, "Referer": f"https://www.regulations.gov/comment/{comment_id}"}
        r = requests.get(pdf_url, timeout=60, headers=headers)
        r.raise_for_status()
        pages_text = []
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages_text.append(t.strip())
        text = "\n\n".join(pages_text).strip()
        scanned = len(pages_text) == 0  # no extractable text layers
        return text, scanned
    except Exception as e:
        print(f"    WARNING: PDF extraction failed ({pdf_url}): {e}", file=sys.stderr)
        return "", False


def fetch_comment_detail(comment_id):
    """Fetch full detail for a single comment, including PDF text if attachment."""
    raw = get(f"{API_BASE}/comments/{comment_id}", {"include": "attachments"})
    attrs = raw.get("data", {}).get("attributes", {})

    inline_text = (attrs.get("comment") or "").strip()
    _ATTACH_HINT = re.compile(
        r'\b(attach(ed|ment|ments)?|see (attached|below)|please (read|see|find))\b',
        re.I
    )
    has_attachment = (
        not inline_text
        or inline_text.lower().startswith("see attached")
        or (len(inline_text) < 400 and bool(_ATTACH_HINT.search(inline_text)))
    )

    pdf_text = ""
    pdf_scanned = False
    pdf_urls = []

    if has_attachment and PDF_SUPPORT:
        pdf_urls = fetch_pdf_urls(comment_id, raw)
        for url in pdf_urls[:1]:  # extract first PDF only
            pdf_text, pdf_scanned = extract_pdf_text(url, comment_id)
            if pdf_text:
                print(f"    Extracted {len(pdf_text)} chars from PDF", file=sys.stderr)
                break

    comment_text = inline_text if not has_attachment else pdf_text

    return {
        "id": comment_id,
        "commenter": _name(attrs),
        "organization": attrs.get("organization") or "",
        "city": attrs.get("city") or "",
        "state_province": attrs.get("stateProvinceRegion") or "",
        "country": attrs.get("country") or "",
        "posted_date": attrs.get("postedDate") or "",
        "received_date": attrs.get("receiveDate") or "",
        "comment_text": comment_text,
        "has_attachment": has_attachment,
        "pdf_extracted": has_attachment and bool(pdf_text),
        "pdf_scanned": pdf_scanned,
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

    # Load existing data — skip re-fetching unless it's an attachment without extracted text yet
    existing = {}
    if OUT_FILE.exists():
        try:
            old = json.loads(OUT_FILE.read_text(encoding="utf-8"))
            for c in old.get("comments", []):
                # Re-fetch attachment comments that haven't had PDF extraction attempted
                if c.get("has_attachment") and not c.get("pdf_extracted") and not c.get("pdf_scanned"):
                    continue  # will re-fetch
                existing[c["id"]] = c
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
            label = detail["commenter"] or detail["organization"] or "Anonymous"
            pdf_note = " [PDF extracted]" if detail.get("pdf_extracted") else (" [PDF scanned/unreadable]" if detail.get("pdf_scanned") else "")
            print(f"  [{i+1}/{len(ids)}] {cid} — {label}{pdf_note}", file=sys.stderr)
            time.sleep(DELAY_BETWEEN_REQUESTS)
        except Exception as e:
            print(f"  WARNING: failed to fetch {cid}: {e}", file=sys.stderr)

    print(f"Fetched {new_count} new/updated comments.", file=sys.stderr)

    pdf_extracted = sum(1 for c in comments if c.get("pdf_extracted"))
    pdf_scanned = sum(1 for c in comments if c.get("pdf_scanned"))
    if pdf_extracted or pdf_scanned:
        print(f"PDF extraction: {pdf_extracted} succeeded, {pdf_scanned} scanned/unreadable", file=sys.stderr)

    output = {
        "docket_id": DOCKET_ID,
        "document_id": DOCUMENT_ID,
        "title": "Restrict the Operation of Unmanned Aircraft in Close Proximity to a Fixed Site Facility",
        "comment_period_end": "2026-08-05",
        "total_comments": len(comments),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "comments": comments,
    }

    json_str = json.dumps(output, indent=2, ensure_ascii=False)
    OUT_FILE.write_text(json_str, encoding="utf-8")
    DATA_JS.write_text(f"const COMMENTS_DATA = {json_str};\n", encoding="utf-8")
    print(f"Wrote {len(comments)} comments to {OUT_FILE} and {DATA_JS.name}", file=sys.stderr)


if __name__ == "__main__":
    main()
