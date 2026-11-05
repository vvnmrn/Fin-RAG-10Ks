"""Validation gates. A failed 'error' check halts the pipeline for that document."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from ingest.download import sha256_file

ERROR_PAGE_MARKERS = ("request rate threshold", "undeclared automated tool", "access denied")


def _check(name: str, passed: bool, detail: str = "", severity: str = "error") -> dict:
    return {"name": name, "passed": bool(passed), "severity": severity, "detail": detail}


def validate_raw(path: Path, manifest_entry: dict | None, min_bytes: int = 200_000) -> list[dict]:
    checks = [_check("file_exists", path.exists(), str(path))]
    if not path.exists():
        return checks
    full = path.read_bytes().decode("utf-8", errors="ignore").lower()
    head = full[:50_000]
    size = path.stat().st_size
    checks += [
        _check("min_size", size >= min_bytes, f"{size} bytes"),
        _check("not_error_page", not any(m in head for m in ERROR_PAGE_MARKERS)),
        _check(
            "looks_like_10k",
            "10-k" in full and "annual report" in full,
            "missing '10-K' or 'annual report'",
        ),
        _check("in_manifest", manifest_entry is not None),
    ]
    if manifest_entry:
        checks.append(_check("sha256_matches", sha256_file(path) == manifest_entry["sha256"]))
    return checks


def validate_parsed(
    chunks: list[dict],
    min_chunks: int = 300,
    min_table_chunks: int = 50,
    max_chars: int = 1500,
    expect_labels: bool = True,
) -> list[dict]:
    n = len(chunks)
    tables = [c for c in chunks if c["type"] == "table"]
    short = [c for c in chunks if c["type"] == "text" and len(c["text"].strip()) < 20]
    ids = [c["chunk_id"] for c in chunks]
    too_long = [c for c in chunks if c["type"] == "text" and c["n_chars"] > max_chars]
    thin_tables = [c for c in tables if all(len(r.split(" | ")) < 2 for r in c["text"].split("\n"))]
    unlabeled = sum(c["section"] == "Unlabeled" for c in chunks) / n if n else 1.0
    digits = sum(bool(re.search(r"\d", c["text"])) for c in tables) / len(tables) if tables else 0.0
    sections = {c["section"] for c in chunks}
    labeled = Counter(c["section"] for c in chunks if c["section"] != "Unlabeled")
    top = max(labeled.values(), default=0) / n if n else 0.0

    checks = [
        _check("min_chunks", n >= min_chunks, f"{n} chunks (need {min_chunks})"),
        _check("min_table_chunks", len(tables) >= min_table_chunks, f"{len(tables)} table chunks"),
        _check("unique_chunk_ids", len(ids) == len(set(ids))),
        _check("no_near_empty_text", len(short) / max(n, 1) < 0.02, f"{len(short)} near-empty"),
        _check("text_chunk_size_cap", not too_long, f"{len(too_long)} over {max_chars} chars"),
        _check("tables_have_columns", len(thin_tables) / max(len(tables), 1) < 0.05, f"{len(thin_tables)} single-column tables"),
        _check("tables_contain_numbers", digits >= 0.9, f"{digits:.0%} of table chunks"),
        # A mislabeled document (one stray 'Item 15' swallowing everything) is worse than an unlabeled one.
        _check("no_dominant_section", top < 0.6 or n < 50, f"largest section holds {top:.0%}"),
    ]
    if expect_labels:
        checks += [
            _check("section_labels", unlabeled < 0.5, f"{unlabeled:.0%} chunks unlabeled", "warning"),
            _check("item_headings_found", len(sections - {"Unlabeled"}) >= 3, f"{sorted(sections)[:8]}", "warning"),
        ]
    return checks


def summarize(checks: list[dict]) -> dict:
    errors = [c for c in checks if not c["passed"] and c["severity"] == "error"]
    warnings = [c for c in checks if not c["passed"] and c["severity"] == "warning"]
    return {"ok": not errors, "n_errors": len(errors), "n_warnings": len(warnings), "checks": checks}
