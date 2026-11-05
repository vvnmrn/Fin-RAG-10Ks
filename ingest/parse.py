"""Parse a 10-K HTML file into text and table chunks. Deterministic: same input, same output."""
from __future__ import annotations

import hashlib
import json
import re
import warnings
from pathlib import Path

from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning

import config

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

ITEM_RE = re.compile(r"^\s*item\s+(\d{1,2}[ab]?)\b", re.I)
PAGE_BREAK_RE = re.compile(r"page-break-(before|after)\s*:\s*always", re.I)
NOISE_RE = re.compile(r"(page\s*)?\d{1,3}|table of contents", re.I)
FOOTNOTE_RE = re.compile(r"\([a-z]\)")
FOOTER_RE = re.compile(r"form 10-k", re.I)
BLOCK_NAMES = {"p", "div", "li", "ul", "ol", "table", "h1", "h2", "h3", "h4", "h5", "h6"}
TEXT_NAMES = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"}
SYMBOLS_PREFIX = {"$", "($", "(", "\u20ac", "\u00a3"}
SYMBOLS_SUFFIX = {")", "%", ")%", "bps"}


def norm(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


_FIXES = [
    (re.compile(r"\(\s+"), "("),
    (re.compile(r"\s+\)"), ")"),
    (re.compile(r"\$\s+(?=[\d(])"), "$"),
    (re.compile(r"\s+%"), "%"),
    (re.compile(r"\s+,"), ","),
]


def clean_cell(text: str) -> str:
    text = norm(text)
    for pat, rep in _FIXES:
        text = pat.sub(rep, text)
    return text


def merge_cells(cells: list[str]) -> list[str]:
    """Drop empty cells and glue '$' / ')' / '%' fragments and footnote markers onto their numbers."""
    out: list[str] = []
    for c in cells:
        if not c:
            continue
        if out and c in SYMBOLS_SUFFIX:
            out[-1] += c
        elif out and FOOTNOTE_RE.fullmatch(c):
            out[-1] += " " + c
        elif out and out[-1] in SYMBOLS_PREFIX:
            out[-1] += c
        else:
            out.append(c)
    return out


def table_rows(table: Tag) -> list[list[str]]:
    rows = []
    for tr in table.find_all("tr"):
        cells = merge_cells([clean_cell(td.get_text(" ")) for td in tr.find_all(["td", "th"])])
        if cells:
            rows.append(cells)
    return rows


def is_page_footer(rows: list[list[str]]) -> bool:
    flat = " ".join(" ".join(r) for r in rows)
    return len(rows) <= 2 and len(flat) < 80 and bool(FOOTER_RE.search(flat))


def iter_blocks(root: Tag):
    """Yield ('page', None), ('table', el) or ('text', el) in document order."""
    for el in root.descendants:
        if not isinstance(el, Tag):
            continue
        if PAGE_BREAK_RE.search(el.get("style", "") or ""):
            yield "page", None
        if el.name == "table":
            if el.find_parent("table") is None:
                yield "table", el
        elif el.name in TEXT_NAMES:
            if el.find_parent("table") or el.find(BLOCK_NAMES):
                continue
            yield "text", el


def split_sentences(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts, cur = [], ""
    for sent in re.split(r"(?<=[.!?])\s+", text):
        while len(sent) > max_chars:  # unbroken run, hard split
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(sent[:max_chars])
            sent = sent[max_chars:]
        if cur and len(cur) + len(sent) + 1 > max_chars:
            parts.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        parts.append(cur)
    return parts


def build_chunks(
    html: str,
    doc_id: str,
    max_chars: int = config.MAX_TEXT_CHARS,
    max_rows: int = config.MAX_TABLE_ROWS,
    label_sections: bool = True,
) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["script", "style", "ix:header"]):
        tag.decompose()
    root = soup.body or soup

    raw: list[tuple[str, str, int, str]] = []  # (type, section, page, text)
    buf: list[str] = []
    buf_page = 1
    section = "Unlabeled"
    page = 1

    def flush():
        nonlocal buf
        if buf:
            for piece in split_sentences(" ".join(buf), max_chars):
                raw.append(("text", section, buf_page, piece))
            buf = []

    def add_text(text: str):
        nonlocal buf_page
        if not buf:
            buf_page = page
        if sum(len(b) for b in buf) + len(text) > max_chars:
            flush()
            buf_page = page
        buf.append(text)

    for kind, el in iter_blocks(root):
        if kind == "page":
            page += 1
        elif kind == "text":
            text = norm(el.get_text(" "))
            if not text or NOISE_RE.fullmatch(text):
                continue
            m = ITEM_RE.match(text)
            if m and len(text) < 150 and label_sections:
                flush()
                section = f"Item {m.group(1).upper()}"
            add_text(text)
        else:
            rows = table_rows(el)
            if not rows or is_page_footer(rows):
                continue
            if all(len(r) == 1 for r in rows):  # layout table holding prose
                for r in rows:
                    if not NOISE_RE.fullmatch(r[0]):
                        add_text(r[0])
                continue
            flush()
            header = rows[0]
            for i in range(0, len(rows), max_rows):
                part = rows[i : i + max_rows]
                if i > 0:
                    part = [header] + part
                raw.append(("table", section, page, "\n".join(" | ".join(r) for r in part)))
    flush()

    return [
        {
            "doc_id": doc_id,
            "chunk_id": f"{doc_id}:{i:05d}",
            "type": t,
            "section": sec,
            "page_approx": pg,
            "text": text,
            "n_chars": len(text),
            "sha1": hashlib.sha1(text.encode()).hexdigest()[:12],
        }
        for i, (t, sec, pg, text) in enumerate(raw)
    ]


def write_jsonl(chunks: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, sort_keys=True, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]
