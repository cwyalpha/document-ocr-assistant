from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Iterable

from .models import OcrBlock, TableResult


def sort_blocks_reading_order(blocks: Iterable[OcrBlock]) -> list[OcrBlock]:
    """Sort OCR boxes into a stable top-to-bottom, column-aware reading order."""
    values = list(blocks)
    if len(values) < 2:
        return values
    heights = sorted(max(1.0, block.bounds[3] - block.bounds[1]) for block in values)
    median_height = heights[len(heights) // 2]
    line_tolerance = max(4.0, median_height * 0.55)
    lines: list[list[OcrBlock]] = []
    for block in sorted(values, key=lambda value: (value.bounds[1], value.bounds[0])):
        center_y = (block.bounds[1] + block.bounds[3]) / 2
        for line in lines:
            first = line[0]
            first_y = (first.bounds[1] + first.bounds[3]) / 2
            if abs(center_y - first_y) <= line_tolerance:
                line.append(block)
                break
        else:
            lines.append([block])
    lines.sort(key=lambda line: min(value.bounds[1] for value in line))
    result: list[OcrBlock] = []
    for line in lines:
        result.extend(sorted(line, key=lambda value: value.bounds[0]))
    return result


def blocks_to_text(blocks: Iterable[OcrBlock], mode: str = "natural") -> str:
    ordered = sort_blocks_reading_order(blocks)
    if mode == "raw":
        return "\n".join(block.text.strip() for block in ordered if block.text.strip())
    paragraphs: list[str] = []
    current: list[str] = []
    previous: OcrBlock | None = None
    for block in ordered:
        text = block.text.strip()
        if not text:
            continue
        if previous:
            gap = block.bounds[1] - previous.bounds[3]
            height = max(1.0, previous.bounds[3] - previous.bounds[1])
            if gap > height * 0.9:
                if current:
                    paragraphs.append("".join(current))
                current = []
        current.append(text)
        previous = block
    if current:
        paragraphs.append("".join(current))
    return "\n\n".join(paragraphs)


class _TableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self.has_span = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"}:
            values = dict(attrs)
            self.has_span = self.has_span or values.get("rowspan", "1") != "1" or values.get("colspan", "1") != "1"
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def html_table_to_markdown(table_html: str) -> str:
    parser = _TableHTMLParser()
    try:
        parser.feed(table_html)
    except Exception:
        return table_html.strip()
    rows = [row for row in parser.rows if row]
    if not rows or parser.has_span:
        return table_html.strip()
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]

    def escape(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ")

    rendered = ["| " + " | ".join(escape(cell) for cell in normalized[0]) + " |"]
    rendered.append("| " + " | ".join("---" for _ in range(width)) + " |")
    rendered.extend("| " + " | ".join(escape(cell) for cell in row) + " |" for row in normalized[1:])
    return "\n".join(rendered)


def html_table_to_text(table_html: str) -> str:
    parser = _TableHTMLParser()
    try:
        parser.feed(table_html)
    except Exception:
        return re.sub(r"<[^>]+>", "", html.unescape(table_html))
    return "\n".join("\t".join(row) for row in parser.rows if row)


class _DocumentWithoutTablesParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.table_depth = 0
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "table":
            self.table_depth += 1
        elif tag in {"script", "style"}:
            self.hidden_depth += 1
        elif not self.table_depth and tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "table" and self.table_depth:
            self.table_depth -= 1
            self.parts.append("\n")
        elif tag in {"script", "style"} and self.hidden_depth:
            self.hidden_depth -= 1
        elif not self.table_depth and tag in {"p", "div", "li", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.table_depth and not self.hidden_depth:
            self.parts.append(data)

    @property
    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.parts).splitlines()]
        return "\n".join(line for line in lines if line).strip()


def html_document_without_tables_to_text(document_html: str) -> str:
    parser = _DocumentWithoutTablesParser()
    try:
        parser.feed(document_html)
    except Exception:
        return ""
    return parser.text


def build_markdown(text: str, tables: Iterable[TableResult], title: str | None = None) -> str:
    sections: list[str] = []
    if title:
        sections.append(f"# {title}")
    if text.strip():
        sections.append(text.strip())
    for index, table in enumerate(tables, start=1):
        sections.append(f"## 表格 {index}\n\n{html_table_to_markdown(table.html)}")
    return "\n\n".join(sections).strip() + "\n"
