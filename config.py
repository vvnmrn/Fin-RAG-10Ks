"""Central settings. Edit COMPANIES / FISCAL_YEARS to change the corpus."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RAW = DATA / "raw"
PARSED = DATA / "parsed"
REPORTS = DATA / "reports"
MANIFEST = DATA / "manifest.json"

# name_fragment is checked against the SEC's registered name, so a wrong CIK fails loudly.
# label_sections=False for filers whose 10-K does not follow the standard Item layout.
COMPANIES = {
    "JPM": {"cik": 19617, "name_fragment": "jpmorgan", "label_sections": False},
    "C": {"cik": 831001, "name_fragment": "citigroup", "label_sections": False},
    "V": {"cik": 1403161, "name_fragment": "visa", "label_sections": True},
    "MA": {"cik": 1141391, "name_fragment": "mastercard", "label_sections": True},
}
# Fiscal year = year of the filing's report date (Visa's FY ends in September).
FISCAL_YEARS = [2024, 2025]

MAX_TEXT_CHARS = 1500
MAX_TABLE_ROWS = 25
