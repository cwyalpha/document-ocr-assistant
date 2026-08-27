from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from typing import Iterable

from .models import OcrBlock


PAGE_MARGIN_RATIO = 0.12
MAX_LINE_HEIGHT_RATIO = 0.08

# OCR engines do not consistently distinguish the many horizontal line glyphs.
# Chinese 一 is included only in the wrapper position because it is a common
# misrecognition of a long dash in page-number decorations.
_DASH_CHARACTERS = "-‐‑‒–—―−﹘﹣－_＿─━~～=一"
_DASH_CLASS = re.escape(_DASH_CHARACTERS)
_DASH_WRAPPER = re.compile(
    rf"^[{_DASH_CLASS}]{{1,3}}(.+?)[{_DASH_CLASS}]{{1,3}}$"
)
_OCR_DIGIT_TRANSLATION = str.maketrans(
    {
        "I": "1",
        "i": "1",
        "l": "1",
        "L": "1",
        "|": "1",
        "丨": "1",
        "O": "0",
        "o": "0",
        "〇": "0",
    }
)
_CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "兩": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_CHINESE_UNITS = {"十": 10, "百": 100, "千": 1000}
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


@dataclass(frozen=True, slots=True)
class PositionedTextLine:
    page_index: int
    text: str
    bbox: tuple[float, float, float, float]
    page_width: float
    page_height: float
    source_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ParsedPageNumber:
    value: int
    strong: bool
    kind: str
    corrected: bool = False
    total: int | None = None


@dataclass(frozen=True, slots=True)
class PageNumberMatch:
    line: PositionedTextLine
    parsed: ParsedPageNumber
    region: str


def _compact(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", "", normalized).strip()


def _parse_chinese_number(value: str) -> int | None:
    if not value or any(
        character not in _CHINESE_DIGITS and character not in _CHINESE_UNITS
        for character in value
    ):
        return None
    if not any(character in _CHINESE_UNITS for character in value):
        digits = "".join(str(_CHINESE_DIGITS[character]) for character in value)
        return int(digits) if digits else None
    total = 0
    current = 0
    for character in value:
        if character in _CHINESE_DIGITS:
            current = _CHINESE_DIGITS[character]
        else:
            unit = _CHINESE_UNITS[character]
            total += (current or 1) * unit
            current = 0
    return total + current


def _parse_roman_number(value: str) -> int | None:
    upper = value.upper()
    if not upper or not re.fullmatch(r"[IVXLCDM]+", upper):
        return None
    total = 0
    previous = 0
    for character in reversed(upper):
        number = _ROMAN_VALUES[character]
        if number < previous:
            total -= number
        else:
            total += number
            previous = number
    return total if 0 < total <= 3999 else None


def _parse_number_token(value: str) -> tuple[int, bool, str] | None:
    if re.fullmatch(r"\d{1,6}", value):
        return int(value), False, "arabic"
    translated = value.translate(_OCR_DIGIT_TRANSLATION)
    if translated != value and re.fullmatch(r"\d{1,6}", translated):
        return int(translated), True, "arabic"
    chinese = _parse_chinese_number(value)
    if chinese is not None:
        return chinese, False, "chinese"
    roman = _parse_roman_number(value)
    if roman is not None:
        return roman, False, "roman"
    return None


def _valid_number(parsed: tuple[int, bool, str] | None) -> tuple[int, bool, str] | None:
    if parsed is None or not 0 < parsed[0] <= 999999:
        return None
    return parsed


def _parse_core(value: str) -> ParsedPageNumber | None:
    chinese = re.fullmatch(r"第(.+?)[页頁](?:共(.+?)[页頁]?)?", value)
    if chinese:
        current = _valid_number(_parse_number_token(chinese.group(1)))
        total = _valid_number(_parse_number_token(chinese.group(2))) if chinese.group(2) else None
        if current and (total is None or current[0] <= total[0]):
            return ParsedPageNumber(
                current[0], True, "chinese-label", current[1], total[0] if total else None
            )

    english = re.fullmatch(r"(?i)(?:page|p\.?)(.+?)(?:of(.+))?", value)
    if english:
        current = _valid_number(_parse_number_token(english.group(1)))
        total = _valid_number(_parse_number_token(english.group(2))) if english.group(2) else None
        if current and (total is None or current[0] <= total[0]):
            return ParsedPageNumber(
                current[0], True, "english-label", current[1], total[0] if total else None
            )

    fraction = re.fullmatch(r"(.+?)/(.+)", value)
    if fraction:
        current = _valid_number(_parse_number_token(fraction.group(1)))
        total = _valid_number(_parse_number_token(fraction.group(2)))
        if current and total and current[0] <= total[0]:
            return ParsedPageNumber(
                current[0], True, "fraction", current[1] or total[1], total[0]
            )

    number = _valid_number(_parse_number_token(value))
    if number:
        return ParsedPageNumber(number[0], False, number[2], number[1])
    return None


def parse_page_number(value: str) -> ParsedPageNumber | None:
    """Parse a complete line as a page number; mixed-content lines are rejected."""
    compact = _compact(value)
    if not compact or len(compact) > 32:
        return None
    # Bracketed numbers are deliberately unsupported to avoid deleting
    # citations and footnotes such as [1].
    if compact[0] in "([（【［" or compact[-1] in ")]）】］":
        return None
    wrapped = _DASH_WRAPPER.fullmatch(compact)
    if wrapped:
        parsed = _parse_core(wrapped.group(1))
        return replace(parsed, strong=True, kind="dash-wrapper") if parsed else None
    return _parse_core(compact)


def _line_region(line: PositionedTextLine) -> str | None:
    if line.page_height <= 0:
        return None
    _x1, y1, _x2, y2 = line.bbox
    height = max(0.0, y2 - y1)
    if height > line.page_height * MAX_LINE_HEIGHT_RATIO:
        return None
    center_y = (y1 + y2) / 2
    if center_y <= line.page_height * PAGE_MARGIN_RATIO:
        return "top"
    if center_y >= line.page_height * (1.0 - PAGE_MARGIN_RATIO):
        return "bottom"
    return None


def find_page_number_matches(
    lines: Iterable[PositionedTextLine], page_count: int
) -> list[PageNumberMatch]:
    """Return conservative page-number matches using position and page sequence."""
    candidates: list[PageNumberMatch] = []
    for line in lines:
        region = _line_region(line)
        parsed = parse_page_number(line.text) if region else None
        if parsed and region:
            candidates.append(PageNumberMatch(line, parsed, region))

    accepted: dict[int, PageNumberMatch] = {
        id(match.line): match for match in candidates if match.parsed.strong
    }
    weak = [match for match in candidates if not match.parsed.strong]
    for match in weak:
        if page_count == 1 and match.parsed.value == 1:
            accepted[id(match.line)] = match
        elif match.parsed.value == match.line.page_index + 1:
            accepted[id(match.line)] = match

    by_sequence: dict[tuple[str, int], list[PageNumberMatch]] = {}
    for match in weak:
        offset = match.parsed.value - (match.line.page_index + 1)
        by_sequence.setdefault((match.region, offset), []).append(match)
    for group in by_sequence.values():
        if len({match.line.page_index for match in group}) >= 2:
            for match in group:
                accepted[id(match.line)] = match

    return sorted(
        accepted.values(),
        key=lambda match: (match.line.page_index, match.line.bbox[1], match.line.bbox[0]),
    )


def ocr_blocks_to_positioned_lines(
    blocks: Iterable[OcrBlock], page_index: int, page_width: float, page_height: float
) -> list[PositionedTextLine]:
    """Group OCR blocks on the same visual row before matching decorations."""
    values = [block for block in blocks if block.text.strip()]
    if not values or page_height <= 0:
        return []
    margin_values = []
    for block in values:
        _x1, y1, _x2, y2 = block.bounds
        center_y = (y1 + y2) / 2
        if center_y <= page_height * PAGE_MARGIN_RATIO or center_y >= page_height * (
            1.0 - PAGE_MARGIN_RATIO
        ):
            margin_values.append(block)
    if not margin_values:
        return []
    heights = sorted(max(1.0, block.bounds[3] - block.bounds[1]) for block in margin_values)
    tolerance = max(3.0, heights[len(heights) // 2] * 0.55)
    rows: list[list[OcrBlock]] = []
    for block in sorted(margin_values, key=lambda item: (item.bounds[1], item.bounds[0])):
        center_y = (block.bounds[1] + block.bounds[3]) / 2
        for row in rows:
            row_center = sum((item.bounds[1] + item.bounds[3]) / 2 for item in row) / len(row)
            if abs(center_y - row_center) <= tolerance:
                row.append(block)
                break
        else:
            rows.append([block])

    result: list[PositionedTextLine] = []
    for row in rows:
        row.sort(key=lambda item: item.bounds[0])
        x1 = min(item.bounds[0] for item in row)
        y1 = min(item.bounds[1] for item in row)
        x2 = max(item.bounds[2] for item in row)
        y2 = max(item.bounds[3] for item in row)
        result.append(
            PositionedTextLine(
                page_index,
                " ".join(item.text.strip() for item in row),
                (x1, y1, x2, y2),
                page_width,
                page_height,
                tuple(id(item) for item in row),
            )
        )
    return result


def native_pdf_text_lines(page, page_index: int) -> list[PositionedTextLine]:
    """Extract positioned native-PDF text lines without importing PyMuPDF globally."""
    result: list[PositionedTextLine] = []
    contents = page.get_text("dict", sort=True)
    for block in contents.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(str(span.get("text", "")) for span in line.get("spans", [])).strip()
            bbox = line.get("bbox")
            if not text or not bbox or len(bbox) != 4:
                continue
            result.append(
                PositionedTextLine(
                    page_index,
                    text,
                    tuple(float(value) for value in bbox),
                    float(page.rect.width),
                    float(page.rect.height),
                    (len(result),),
                )
            )
    return result
