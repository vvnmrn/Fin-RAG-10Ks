"""Central settings. Edit COMPANIES / FISCAL_YEARS to change the corpus."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RAW = DATA / "raw"
PARSED = DATA / "parsed"
REPORTS = DATA / "reports"
MANIFEST = DATA / "manifest.json"

# name_fragment is checked against the SEC's registered name, so a wrong CIK fails loudly.
COMPANIES = {
    "JPM": {"cik": 19617, "name_fragment": "jpmorgan"},
    "C": {"cik": 831001, "name_fragment": "citigroup"},
    "V": {"cik": 1403161, "name_fragment": "visa"},
    "MA": {"cik": 1141391, "name_fragment": "mastercard"},
}
# Fiscal year = year of the filing's report date (Visa's FY ends in September).
FISCAL_YEARS = [2024, 2025]

MAX_TEXT_CHARS = 1500
MAX_TABLE_ROWS = 25
