"""Usage: py inspect_chunks.py JPM_FY2025   (checks parse coverage and prints sample tables)"""
import collections
import json
import sys
import warnings

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

doc = sys.argv[1] if len(sys.argv) > 1 else "V_FY2025"
chunks = [json.loads(l) for l in open(f"data/parsed/{doc}.jsonl", encoding="utf-8")]
print("chunks:", len(chunks), dict(collections.Counter(c["type"] for c in chunks)))
print("sections:", collections.Counter(c["section"] for c in chunks).most_common(12))
print("max page_approx:", max(c["page_approx"] for c in chunks))

parsed_chars = sum(c["n_chars"] for c in chunks)
html = open(f"data/raw/{doc}.htm", encoding="utf-8", errors="ignore").read()
soup = BeautifulSoup(html, "lxml")
for t in soup.find_all(["script", "style", "ix:header"]):
    t.decompose()
visible = len(" ".join(soup.get_text(" ").split()))
print(f"coverage: {parsed_chars / visible:.0%} ({parsed_chars} of {visible} visible chars)")

footers = [c for c in chunks if "form 10-k" in c["text"].lower() and c["n_chars"] < 80]
print("page-footer chunks left:", len(footers))

tables = [c for c in chunks if c["type"] == "table"]
for c in tables[:: max(1, len(tables) // 5)][:5]:
    print("\n---", c["chunk_id"], c["section"], "page~", c["page_approx"])
    print(c["text"][:500])
