"""Download 10-K primary documents from SEC EDGAR and record them in a hashed manifest."""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

import config

SUBMISSIONS = "https://data.sec.gov/submissions/{name}"
ARCHIVES = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
PAUSE_S = 0.2  # SEC asks for <= 10 requests/second


def make_session() -> requests.Session:
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua:
        raise SystemExit("Set SEC_USER_AGENT to 'Your Name your@email.com' (SEC requires it).")
    s = requests.Session()
    s.headers.update({"User-Agent": ua, "Accept-Encoding": "gzip, deflate"})
    return s


def _get(s: requests.Session, url: str) -> requests.Response:
    for attempt in range(3):
        r = s.get(url, timeout=60)
        if r.status_code == 200:
            time.sleep(PAUSE_S)
            return r
        if r.status_code in (429, 503):
            time.sleep(2 * (attempt + 1))
            continue
        r.raise_for_status()
    raise RuntimeError(f"Failed after retries: {url}")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_manifest() -> dict:
    if config.MANIFEST.exists():
        return json.loads(config.MANIFEST.read_text())
    return {}


def save_manifest(manifest: dict) -> None:
    config.DATA.mkdir(parents=True, exist_ok=True)
    tmp = config.MANIFEST.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    tmp.replace(config.MANIFEST)  # atomic


def list_10k_filings(s: requests.Session, cik: int, name_fragment: str, min_year: int) -> list[dict]:
    main = _get(s, SUBMISSIONS.format(name=f"CIK{cik:010d}.json")).json()
    if name_fragment.lower() not in main["name"].lower():
        raise ValueError(f"CIK {cik} is registered as {main['name']!r}, expected {name_fragment!r}")
    blocks = [main["filings"]["recent"]]
    for f in main["filings"].get("files", []):
        if f.get("filingTo", "9999") >= f"{min_year}-01-01":
            blocks.append(_get(s, SUBMISSIONS.format(name=f["name"])).json())
    out = []
    for b in blocks:
        for i, form in enumerate(b["form"]):
            if form == "10-K" and b["reportDate"][i]:
                out.append(
                    {
                        "accession": b["accessionNumber"][i],
                        "report_date": b["reportDate"][i],
                        "filing_date": b["filingDate"][i],
                        "primary_document": b["primaryDocument"][i],
                        "fiscal_year": int(b["reportDate"][i][:4]),
                        "registered_name": main["name"],
                    }
                )
    return out


def download_filing(s, ticker: str, cik: int, filing: dict, manifest: dict) -> tuple[str, bool]:
    """Returns (doc_id, downloaded). Skips when the file exists and its hash matches the manifest."""
    doc_id = f"{ticker}_FY{filing['fiscal_year']}"
    path = config.RAW / f"{doc_id}.htm"
    entry = manifest.get(doc_id)
    if entry and path.exists() and sha256_file(path) == entry["sha256"]:
        return doc_id, False
    url = ARCHIVES.format(
        cik=cik, acc=filing["accession"].replace("-", ""), doc=filing["primary_document"]
    )
    r = _get(s, url)
    config.RAW.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    manifest[doc_id] = {
        **filing,
        "ticker": ticker,
        "cik": cik,
        "url": url,
        "path": str(path.relative_to(config.ROOT)),
        "bytes": len(r.content),
        "sha256": sha256_file(path),
        "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return doc_id, True
