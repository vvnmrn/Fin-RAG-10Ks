from ingest import parse, validate

HTML = """
<html><body>
<ix:header><div>hidden xbrl junk 12345</div></ix:header>
<div>Table of Contents</div>
<div>Item 1A. Risk Factors</div>
<div>Credit losses could rise. We monitor exposure closely. Page text continues here.</div>
<div style="page-break-after:always"></div>
<div>Item 7. Management's Discussion</div>
<table>
  <tr><td>(in millions)</td><td>2025</td><td>2024</td></tr>
  <tr><td>Net revenue</td><td>$</td><td>1,234</td><td>$</td><td>1,100</td></tr>
  <tr><td>Net loss</td><td>$</td><td>(56</td><td>)</td><td>12</td><td>%</td></tr>
</table>
<table><tr><td>A layout table holding a single prose paragraph of text.</td></tr></table>
<div>42</div>
</body></html>
"""


def test_merge_cells_glues_symbols():
    assert parse.merge_cells(["Net revenue", "$", "1,234", "", "$", "(56", ")"]) == [
        "Net revenue", "$1,234", "$(56)"
    ]


def test_parse_sections_tables_and_noise():
    chunks = parse.build_chunks(HTML, "T_FY2025")
    texts = " ".join(c["text"] for c in chunks)
    assert "hidden xbrl" not in texts
    assert "Table of Contents" not in texts
    assert not any(c["text"] == "42" for c in chunks)
    tables = [c for c in chunks if c["type"] == "table"]
    assert len(tables) == 1 and "Net revenue | $1,234 | $1,100" in tables[0]["text"]
    assert tables[0]["section"] == "Item 7"
    assert any(c["section"] == "Item 1A" for c in chunks)
    assert tables[0]["page_approx"] == 2
    assert "layout table holding" in texts  # prose in layout table kept as text


def test_parse_is_deterministic():
    assert parse.build_chunks(HTML, "T") == parse.build_chunks(HTML, "T")


def test_long_text_is_split_under_cap():
    html = "<html><body><div>" + ("This is a sentence. " * 400) + "</div></body></html>"
    chunks = parse.build_chunks(html, "T", max_chars=500)
    assert len(chunks) > 1 and all(c["n_chars"] <= 500 for c in chunks)


def test_table_split_repeats_header():
    rows = "".join(f"<tr><td>r{i}</td><td>{i}</td></tr>" for i in range(60))
    html = f"<html><body><table><tr><td>name</td><td>val</td></tr>{rows}</table></body></html>"
    tables = [c for c in parse.build_chunks(html, "T", max_rows=25) if c["type"] == "table"]
    assert len(tables) >= 3 and all(c["text"].startswith("name | val") for c in tables)


def test_parsed_gate_passes_good_and_fails_bad():
    good = parse.build_chunks(HTML, "T")
    res = validate.summarize(validate.validate_parsed(good, min_chunks=2, min_table_chunks=1))
    assert res["ok"]
    bad = good + [dict(good[0])]  # duplicate chunk id
    res = validate.summarize(validate.validate_parsed(bad, min_chunks=2, min_table_chunks=1))
    assert not res["ok"]
    assert any(c["name"] == "unique_chunk_ids" and not c["passed"] for c in res["checks"])


def test_raw_gate_rejects_sec_error_page(tmp_path):
    p = tmp_path / "x.htm"
    p.write_text("<html>Request Rate Threshold Exceeded" + "x" * 300_000 + "</html>")
    res = validate.summarize(validate.validate_raw(p, None))
    assert not res["ok"]
    assert any(c["name"] == "not_error_page" and not c["passed"] for c in res["checks"])
