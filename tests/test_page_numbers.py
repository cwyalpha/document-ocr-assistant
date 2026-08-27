from __future__ import annotations

from pathlib import Path

import fitz
from PIL import Image

from document_ocr_assistant.cli import build_parser
from document_ocr_assistant.models import (
    InputItem,
    InputKind,
    OcrBlock,
    PageOrientation,
    PdfMode,
    ProcessingOptions,
)
from document_ocr_assistant.orientation import OrientationEngine
from document_ocr_assistant.page_numbers import (
    PositionedTextLine,
    find_page_number_matches,
    ocr_blocks_to_positioned_lines,
    parse_page_number,
)
from document_ocr_assistant.processors import DocumentProcessors


class NoTables:
    available = False

    def analyze(self, *_args, **_kwargs):
        return []


class FooterOcr:
    def recognize(self, image, page_index=0, options=None):
        height, width = image.shape[:2]
        body = "ALPHA BODY" if page_index == 0 else "BETA BODY"
        return [
            OcrBlock(body, [[20, 80], [250, 80], [250, 115], [20, 115]], 0.99, page_index),
            OcrBlock("—", [[width / 2 - 45, height - 35], [width / 2 - 30, height - 35], [width / 2 - 30, height - 15], [width / 2 - 45, height - 15]], 0.91, page_index),
            OcrBlock(str(page_index + 1), [[width / 2 - 20, height - 35], [width / 2, height - 35], [width / 2, height - 15], [width / 2 - 20, height - 15]], 0.92, page_index),
            OcrBlock("-", [[width / 2 + 10, height - 35], [width / 2 + 25, height - 35], [width / 2 + 25, height - 15], [width / 2 + 10, height - 15]], 0.90, page_index),
        ]


def _line(page_index: int, text: str, y: float = 930, x: float = 450) -> PositionedTextLine:
    return PositionedTextLine(
        page_index,
        text,
        (x, y, x + 100, y + 25),
        1000,
        1000,
        (page_index,),
    )


def test_page_number_format_matrix_and_ocr_tolerance() -> None:
    values = {
        "- 1 -": 1,
        "—1-": 1,
        "- 1—": 1,
        "－  1 -": 1,
        "_1—": 1,
        "— I -": 1,
        "第 12 页": 12,
        "第十二頁": 12,
        "Page 3": 3,
        "P. 4": 4,
        "Page O5 of 20": 5,
        "6 / 20": 6,
        "第7页 共20页": 7,
        "VIII": 8,
        "九": 9,
    }
    for text, expected in values.items():
        parsed = parse_page_number(text)
        assert parsed is not None, text
        assert parsed.value == expected, text

    for text in ("(1)", "[1]", "【1】", "正文 1", "2026 年", "金额 100"):
        assert parse_page_number(text) is None


def test_position_and_sequence_rules_for_bare_numbers() -> None:
    lines = [
        _line(2, "1", x=20),
        _line(4, "3", x=880),
        _line(1, "99"),
        _line(0, "1", y=450),
    ]
    matches = find_page_number_matches(lines, page_count=6)
    assert {(match.line.page_index, match.parsed.value) for match in matches} == {
        (2, 1),
        (4, 3),
    }
    physical = find_page_number_matches([_line(2, "3")], page_count=5)
    assert len(physical) == 1
    single = find_page_number_matches([_line(0, "1")], page_count=1)
    assert len(single) == 1
    assert not find_page_number_matches([_line(0, "2")], page_count=1)


def test_journal_page_numbers_may_start_from_an_arbitrary_number() -> None:
    lines = [
        _line(0, "101", x=880),
        _line(1, "102", x=20),
        _line(2, "103", x=880),
    ]
    matches = find_page_number_matches(lines, page_count=3)
    assert [match.parsed.value for match in matches] == [101, 102, 103]


def test_split_ocr_dash_line_is_grouped_and_removed() -> None:
    blocks = [
        OcrBlock("—", [[400, 930], [420, 930], [420, 950], [400, 950]]),
        OcrBlock("I", [[430, 930], [445, 930], [445, 950], [430, 950]]),
        OcrBlock("-", [[455, 930], [475, 930], [475, 950], [455, 950]]),
    ]
    lines = ocr_blocks_to_positioned_lines(blocks, 0, 1000, 1000)
    assert len(lines) == 1
    matches = find_page_number_matches(lines, page_count=1)
    assert len(matches) == 1
    assert set(matches[0].line.source_ids) == {id(block) for block in blocks}


def test_native_pdf_page_numbers_are_removed_from_text_and_markdown(tmp_path: Path) -> None:
    source = tmp_path / "native-pages.pdf"
    document = fitz.open()
    for number in range(1, 4):
        page = document.new_page(width=400, height=600)
        page.insert_text((40, 100), f"Native body page {number} with enough searchable content for extraction.")
        page.insert_text((185, 575), f"- {number} -")
    document.save(source)
    document.close()

    processors = DocumentProcessors(table_engine=NoTables())
    original = processors.process(
        InputItem(source, InputKind.PDF),
        ProcessingOptions(pdf_mode=PdfMode.TEXT_ONLY, table_detection=False),
    )
    assert "- 1 -" in original.text

    cleaned = processors.process(
        InputItem(source, InputKind.PDF),
        ProcessingOptions(
            pdf_mode=PdfMode.TEXT_ONLY,
            table_detection=False,
            remove_pdf_page_numbers=True,
        ),
    )
    assert "Native body page 1" in cleaned.text
    assert "- 1 -" not in cleaned.text
    assert "- 2 -" not in cleaned.markdown
    assert cleaned.raw_text == cleaned.text
    assert [page["removed_page_number_count"] for page in cleaned.metadata["pages"]] == [1, 1, 1]

    relabeled = processors.process(
        InputItem(source, InputKind.PDF),
        ProcessingOptions(
            pdf_mode=PdfMode.TEXT_ONLY,
            table_detection=False,
            remove_pdf_page_numbers=True,
            include_page_numbers=True,
        ),
    )
    assert relabeled.text.startswith("第 1 页\n\nNative body page 1")
    assert "- 1 -" not in relabeled.text


def test_scanned_pdf_removes_split_footer_from_all_text_layers(tmp_path: Path) -> None:
    image = tmp_path / "scan.png"
    Image.new("RGB", (320, 180), "white").save(image)
    source = tmp_path / "scanned-pages.pdf"
    document = fitz.open()
    for _ in range(2):
        page = document.new_page(width=320, height=180)
        page.insert_image(page.rect, filename=str(image))
    document.save(source)
    document.close()

    processors = DocumentProcessors(FooterOcr(), NoTables(), OrientationEngine())
    result = processors.process(
        InputItem(source, InputKind.PDF),
        ProcessingOptions(
            pdf_mode=PdfMode.FORCE_OCR,
            searchable_pdf=True,
            table_detection=False,
            page_orientation=PageOrientation.OFF,
            remove_pdf_page_numbers=True,
        ),
    )
    assert "ALPHA BODY" in result.text and "BETA BODY" in result.text
    assert "\n1\n" not in f"\n{result.text}\n"
    assert len(result.blocks) == 2
    assert all("—" not in block.text and block.text != "-" for block in result.blocks)
    assert [page["removed_page_number_count"] for page in result.metadata["pages"]] == [1, 1]
    with fitz.open(stream=result.searchable_pdf_bytes, filetype="pdf") as searchable:
        text = "\n".join(page.get_text() for page in searchable)
    assert "ALPHA BODY" in text and "BETA BODY" in text
    assert "—" not in text
    assert "\n1\n" not in f"\n{text}\n"


def test_cli_page_number_removal_is_opt_in() -> None:
    parser = build_parser()
    assert parser.parse_args(["sample.pdf"]).remove_pdf_page_numbers is False
    assert parser.parse_args(
        ["--remove-pdf-page-numbers", "sample.pdf"]
    ).remove_pdf_page_numbers is True
