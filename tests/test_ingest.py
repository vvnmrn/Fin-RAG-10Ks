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


def test_footnote_markers_attach_to_previous_cell():
    assert parse.merge_cells(["Gain on Visa shares", "\u2014", "7,990", "(b)", "\u2014"]) == [
        "Gain on Visa shares", "\u2014", "7,990 (b)", "\u2014"
    ]


def test_clean_cell_fixes_spacing():
    assert parse.clean_cell("( 15,751 )") == "(15,751)"
    assert parse.clean_cell("$ 1,893") == "$1,893"
    assert parse.clean_cell("5 %") == "5%"
    assert parse.clean_cell("December 31 , 2025") == "December 31, 2025"
    assert parse.clean_cell("$ per share") == "$ per share"


def test_page_footer_detected():
    assert parse.is_page_footer([["160", "JPMorgan Chase & Co./2025 Form 10-K"]])
    assert not parse.is_page_footer([["Net revenue", "$40,000", "$35,926"]])


def test_page_footer_table_is_dropped():
    html = (
        "<html><body><table><tr><td>160</td><td>JPMorgan Chase &amp; Co./2025 Form 10-K</td></tr></table>"
        "<div>Real content that stays in the output.</div></body></html>"
    )
    chunks = parse.build_chunks(html, "T")
    assert len(chunks) == 1 and "Real content" in chunks[0]["text"]


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


def test_label_sections_off_leaves_everything_unlabeled():
    chunks = parse.build_chunks(HTML, "T", label_sections=False)
    assert {c["section"] for c in chunks} == {"Unlabeled"}


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


def test_dominant_section_is_an_error():
    chunks = [
        {"chunk_id": f"T:{i}", "type": "text", "section": "Item 15", "n_chars": 50, "text": "x" * 50}
        for i in range(100)
    ]
    res = validate.summarize(validate.validate_parsed(chunks, min_chunks=2, min_table_chunks=0))
    assert any(c["name"] == "no_dominant_section" and not c["passed"] for c in res["checks"])


def test_expect_labels_false_skips_label_warnings():
    chunks = parse.build_chunks(HTML, "T", label_sections=False)
    checks = validate.validate_parsed(chunks, min_chunks=2, min_table_chunks=1, expect_labels=False)
    assert not any(c["name"] in ("section_labels", "item_headings_found") for c in checks)


def test_raw_gate_rejects_sec_error_page(tmp_path):
    p = tmp_path / "x.htm"
    p.write_text("<html>Request Rate Threshold Exceeded" + "x" * 300_000 + "</html>")
    res = validate.summarize(validate.validate_raw(p, None))
    assert not res["ok"]
    assert any(c["name"] == "not_error_page" and not c["passed"] for c in res["checks"])


def test_raw_gate_finds_10k_marker_beyond_first_50kb(tmp_path):
    p = tmp_path / "x.htm"
    p.write_text("<html>" + "x" * 120_000 + " ANNUAL REPORT on FORM 10-K " + "y" * 120_000 + "</html>")
    res = validate.validate_raw(p, None)
    assert next(c for c in res if c["name"] == "looks_like_10k")["passed"]
