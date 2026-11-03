# finrag

Auditable RAG over public SEC 10-K filings (JPMorgan, Citi, Visa, Mastercard). Status: ingestion stage only.

## Quick start
```
pip install -r requirements.txt
export SEC_USER_AGENT="Your Name your@email.com"   # SEC requires a contact in the User-Agent
python -m ingest.run --tickers V --years 2025       # try ONE filing first
python -m pytest -q
```
Stages: `--stage download | parse | validate | all`. Reruns skip files whose SHA-256 matches `data/manifest.json`, and parsing is deterministic.

## Validation gates (reports in `data/reports/`)
- **Raw gate:** file exists, size, not an SEC error page, looks like a 10-K, hash matches manifest. Failure halts that document.
- **Parsed gate:** chunk and table counts, unique ids, size cap, tables have columns and numbers. Failure exits non-zero.
- Warnings (not failures): unlabeled sections, missing Item headings.

## Known limitations (keep updating)
- Downloader has not been tested against live EDGAR from the build sandbox. Verify on one filing before running all eight.
- JPMorgan and Citi use non-standard 10-K layouts, so Item labels will likely be missing. Expect warnings.
- Page numbers are approximate (HTML page-break counting), so citations use section plus chunk id until page mapping is verified.
- Blank table cells are dropped, which can misalign sparse columns. Check a few tables by eye against the source.

## Next
1. Run on one filing, read 20 parsed table chunks by eye, fix parser issues.
2. Write `eval/questions.jsonl` (30 questions first) before building any retriever.
3. BM25 baseline, then dense, then hybrid. Log metrics on every change.
