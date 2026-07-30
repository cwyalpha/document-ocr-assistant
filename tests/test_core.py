from __future__ import annotations

from datetime import datetime
from pathlib import Path

from document_ocr_assistant.history import HistoryStore
from document_ocr_assistant.inputs import (
    classify_path,
    collect_passthrough_files,
    expand_inputs,
)
from document_ocr_assistant.models import (
    InputItem,
    InputKind,
    OcrBlock,
    OutputMode,
    PassthroughFile,
    ProcessingOptions,
    TableResult,
)
from document_ocr_assistant.outputs import (
    copy_passthrough_files,
    create_batch_directory,
    output_path,
)
from document_ocr_assistant.settings import AppSettings, SettingsStore
from document_ocr_assistant.text_format import (
    blocks_to_text,
    html_document_without_tables_to_text,
    html_table_to_markdown,
)


def test_input_classification_and_directory_expansion(tmp_path: Path) -> None:
    folder = tmp_path / "资料"
    nested = folder / "合同"
    nested.mkdir(parents=True)
    (nested / "scan.PNG").write_bytes(b"image")
    (nested / "report.DOCX").write_bytes(b"word")
    (nested / "ignore.exe").write_bytes(b"ignored")

    items, unsupported = expand_inputs([folder])

    assert [item.kind for item in items] == [InputKind.WORD, InputKind.IMAGE]
    assert [item.virtual_path.as_posix() for item in items if item.virtual_path] == [
        "合同/report.DOCX",
        "合同/scan.PNG",
    ]
    assert unsupported == [nested / "ignore.exe"]
    assert classify_path(Path("bundle.tar.gz")) is InputKind.ARCHIVE


def test_output_mapping_preserves_folder_and_archive_hierarchy(tmp_path: Path) -> None:
    batch = tmp_path / "output"
    options = ProcessingOptions(
        output_mode=OutputMode.NEW_BATCH_DIRECTORY,
        batch_directory=batch,
    )
    source_root = tmp_path / "input"
    source = source_root / "a" / "scan.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"x")
    ordinary = InputItem(
        source,
        InputKind.IMAGE,
        root_path=source_root,
        virtual_path=Path("a/scan.png"),
    )
    assert output_path(ordinary, options, ".txt") == batch / "input" / "a" / "scan_ocr.txt"

    archive = tmp_path / "source.zip"
    archived = InputItem(
        source,
        InputKind.IMAGE,
        virtual_path=Path("inside/a.png"),
        archive_path=archive,
    )
    assert output_path(archived, options, ".md") == batch / "source_ocr" / "inside" / "a_ocr.md"


def test_batch_directory_is_unique(tmp_path: Path) -> None:
    now = datetime(2026, 7, 17, 10, 30, 0)
    first = create_batch_directory(tmp_path, now)
    second = create_batch_directory(tmp_path, now)
    assert first.name == "批次-20260717-103000"
    assert second.name == "批次-20260717-103000-2"


def test_unconverted_directory_files_are_mapped_and_copied(tmp_path: Path) -> None:
    source_root = tmp_path / "原始资料"
    nested = source_root / "附件"
    nested.mkdir(parents=True)
    (nested / "scan.png").write_bytes(b"image")
    (nested / "说明.txt").write_text("保留文本", encoding="utf-8")
    (nested / "数据.json").write_text('{"ok": true}', encoding="utf-8")
    (nested / "表格.xlsx").write_bytes(b"xlsx-placeholder")

    _items, unsupported = expand_inputs([source_root])
    passthrough = collect_passthrough_files([source_root], unsupported)

    assert [item.virtual_path.as_posix() for item in passthrough] == [
        "附件/数据.json",
        "附件/表格.xlsx",
        "附件/说明.txt",
    ]
    batch = tmp_path / "批次"
    options = ProcessingOptions(
        output_mode=OutputMode.NEW_BATCH_DIRECTORY,
        batch_directory=batch,
        copy_unconverted_files=True,
    )
    outputs = copy_passthrough_files(passthrough, options)

    assert outputs == [batch / source_root.name / item.virtual_path for item in passthrough]
    assert (batch / source_root.name / "附件" / "说明.txt").read_text(encoding="utf-8") == "保留文本"
    assert (batch / source_root.name / "附件" / "数据.json").read_text(encoding="utf-8") == '{"ok": true}'
    assert (batch / source_root.name / "附件" / "表格.xlsx").read_bytes() == b"xlsx-placeholder"


def test_copy_unconverted_is_disabled_by_default_and_for_alongside_mode(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_text("unchanged", encoding="utf-8")
    item = PassthroughFile(source, Path("note.txt"), root_path=tmp_path)
    default_options = ProcessingOptions(batch_directory=tmp_path / "default-output")
    assert copy_passthrough_files([item], default_options) == []
    assert not (tmp_path / "default-output").exists()

    alongside_options = ProcessingOptions(
        output_mode=OutputMode.ALONGSIDE_SOURCE,
        copy_unconverted_files=True,
    )
    assert copy_passthrough_files([item], alongside_options) == []


def test_reading_order_and_markdown_tables() -> None:
    blocks = [
        OcrBlock("B", [[100, 10], [120, 10], [120, 30], [100, 30]]),
        OcrBlock("A", [[10, 10], [30, 10], [30, 30], [10, 30]]),
        OcrBlock("C", [[10, 70], [30, 70], [30, 90], [10, 90]]),
    ]
    assert blocks_to_text(blocks) == "AB\n\nC"
    simple = "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
    assert html_table_to_markdown(simple) == "| A | B |\n| --- | --- |\n| 1 | 2 |"
    merged = '<table><tr><td rowspan="2">A</td><td>B</td></tr></table>'
    assert html_table_to_markdown(merged) == merged
    document = "<html><body><p>Before</p><table><tr><td>cell</td></tr></table><p>After</p></body></html>"
    assert html_document_without_tables_to_text(document) == "Before\nAfter"


def test_settings_roundtrip_and_history_limit(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    store = SettingsStore(settings_path)
    assert AppSettings().copy_unconverted_files is False
    assert AppSettings().remember_close_choice is False
    settings = AppSettings(
        table_detection=False,
        copy_unconverted_files=True,
        remember_close_choice=True,
        close_to_tray=False,
        theme="dark",
    )
    store.save(settings)
    loaded = store.load()
    assert loaded.table_detection is False
    assert loaded.copy_unconverted_files is True
    assert loaded.remember_close_choice is True
    assert loaded.close_to_tray is False
    assert loaded.theme == "dark"

    history = HistoryStore(tmp_path / "history.sqlite3", limit=2)
    history.add("one")
    history.add("two")
    history.add("three")
    assert [entry.text for entry in history.list()] == ["three", "two"]
