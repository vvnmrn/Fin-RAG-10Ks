"""CLI: python -m ingest.run --tickers JPM V --years 2025 [--stage download|parse|validate|all]"""
from __future__ import annotations

import argparse
import json
import sys

import config
from ingest import download, parse, validate


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="+", default=list(config.COMPANIES))
    ap.add_argument("--years", nargs="+", type=int, default=config.FISCAL_YEARS)
    ap.add_argument("--stage", choices=["download", "parse", "validate", "all"], default="all")
    args = ap.parse_args(argv)
    run = lambda s: args.stage in (s, "all")

    manifest = download.load_manifest()

    if run("download"):
        s = download.make_session()
        for t in args.tickers:
            cfg = config.COMPANIES[t]
            filings = download.list_10k_filings(s, cfg["cik"], cfg["name_fragment"], min(args.years))
            for fy in args.years:
                match = [f for f in filings if f["fiscal_year"] == fy]
                if not match:
                    print(f"[{t} FY{fy}] no 10-K found")
                    continue
                doc_id, fresh = download.download_filing(s, t, cfg["cik"], match[0], manifest)
                download.save_manifest(manifest)
                print(f"[{doc_id}] {'downloaded' if fresh else 'unchanged, skipped'}")

    failed = False
    for t in args.tickers:
        for fy in args.years:
            doc_id = f"{t}_FY{fy}"
            raw_path = config.RAW / f"{doc_id}.htm"
            report = {"doc_id": doc_id}

            if run("validate") or run("parse"):
                raw_sum = validate.summarize(validate.validate_raw(raw_path, manifest.get(doc_id)))
                report["raw"] = raw_sum
                if not raw_sum["ok"]:
                    print(f"[{doc_id}] RAW GATE FAILED, halting this document")
                    failed = True
                    _write_report(doc_id, report)
                    continue

            out = config.PARSED / f"{doc_id}.jsonl"
            if run("parse"):
                chunks = parse.build_chunks(raw_path.read_text(encoding="utf-8", errors="ignore"), doc_id)
                parse.write_jsonl(chunks, out)
                print(f"[{doc_id}] parsed {len(chunks)} chunks")

            if run("validate") and out.exists():
                chunks = parse.read_jsonl(out)
                parsed_sum = validate.summarize(validate.validate_parsed(chunks))
                report["parsed"] = parsed_sum
                for c in parsed_sum["checks"]:
                    if not c["passed"]:
                        print(f"  {c['severity'].upper()}: {c['name']} ({c['detail']})")
                print(f"[{doc_id}] parsed gate: {'OK' if parsed_sum['ok'] else 'FAILED'}")
                failed |= not parsed_sum["ok"]
            _write_report(doc_id, report)
    return 1 if failed else 0


def _write_report(doc_id: str, report: dict) -> None:
    config.REPORTS.mkdir(parents=True, exist_ok=True)
    (config.REPORTS / f"{doc_id}.json").write_text(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main())
