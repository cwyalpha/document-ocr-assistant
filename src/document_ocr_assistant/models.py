from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4


class InputKind(str, Enum):
    IMAGE = "image"
    PDF = "pdf"
    WORD = "word"
    ARCHIVE = "archive"
    UNSUPPORTED = "unsupported"


class TaskState(str, Enum):
    PENDING = "等待"
    RUNNING = "处理中"
    PAUSED = "已暂停"
    SUCCEEDED = "已完成"
    WARNING = "有警告"
    FAILED = "失败"
    CANCELLED = "已取消"


class OutputMode(str, Enum):
    NEW_BATCH_DIRECTORY = "new_batch_directory"
    ALONGSIDE_SOURCE = "alongside_source"


class PdfMode(str, Enum):
    AUTO = "auto"
    FORCE_OCR = "force_ocr"
    TEXT_ONLY = "text_only"


class ProductEdition(str, Enum):
    OCR = "ocr"
    FULL = "full"


class OcrPreset(str, Enum):
    FAST = "fast"
    BALANCED = "balanced"
    ACCURATE = "accurate"
    CUSTOM = "custom"


class PageOrientation(str, Enum):
    AUTO = "auto"
    OFF = "off"
    ROTATE_0 = "0"
    ROTATE_90 = "90"
    ROTATE_180 = "180"
    ROTATE_270 = "270"


class LayoutMode(str, Enum):
    MULTI_PARAGRAPH = "multi_paragraph"
    MULTI_LINES = "multi_lines"
    SINGLE_PARAGRAPH = "single_paragraph"
    SINGLE_LINES = "single_lines"
    CODE = "code"
    RAW = "raw"


@dataclass(slots=True)
class OcrBlock:
    text: str
    polygon: list[list[float]]
    score: float = 1.0
    page_index: int = 0

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        xs = [point[0] for point in self.polygon]
        ys = [point[1] for point in self.polygon]
        return min(xs), min(ys), max(xs), max(ys)


@dataclass(slots=True)
class TableResult:
    html: str
    page_index: int = 0
    bbox: tuple[float, float, float, float] | None = None
    confidence: float | None = None


@dataclass(slots=True)
class InputItem:
    source_path: Path
    kind: InputKind
    root_path: Path | None = None
    virtual_path: Path | None = None
    archive_path: Path | None = None
    id: str = field(default_factory=lambda: uuid4().hex)

    @property
    def display_path(self) -> str:
        if self.archive_path and self.virtual_path:
            return f"{self.archive_path.name} / {self.virtual_path.as_posix()}"
        return str(self.source_path)


@dataclass(slots=True)
class PassthroughFile:
    source_path: Path
    virtual_path: Path
    root_path: Path | None = None
    archive_path: Path | None = None


@dataclass(slots=True)
class TaskRecord:
    item: InputItem
    state: TaskState = TaskState.PENDING
    progress: int = 0
    message: str = ""
    text: str = ""
    markdown: str = ""
    outputs: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocks: list[OcrBlock] = field(default_factory=list)
    raw_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProcessResult:
    text: str
    markdown: str
    blocks: list[OcrBlock] = field(default_factory=list)
    tables: list[TableResult] = field(default_factory=list)
    searchable_pdf_bytes: bytes | None = None
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""


@dataclass(slots=True)
class ProcessingOptions:
    output_mode: OutputMode = OutputMode.NEW_BATCH_DIRECTORY
    output_parent: Path | None = None
    batch_directory: Path | None = None
    pdf_mode: PdfMode = PdfMode.AUTO
    searchable_pdf: bool = False
    table_detection: bool = True
    copy_unconverted_files: bool = False
    layout_mode: str = LayoutMode.MULTI_PARAGRAPH.value
    ocr_preset: OcrPreset = OcrPreset.BALANCED
    page_orientation: PageOrientation = PageOrientation.AUTO
    orientation_confidence: float = 0.35
    textline_orientation: bool = True
    pdf_dpi: int = 200
    max_side_len: int = 2000
    det_limit_side_len: int = 736
    det_limit_type: str = "min"
    det_thresh: float = 0.3
    det_box_thresh: float = 0.5
    det_unclip_ratio: float = 1.6
    text_score: float = 0.5
    rec_batch_size: int = 6
    cpu_threads: int = 0
    page_range: str = ""

    def resolved_ocr_values(self) -> dict[str, int | float]:
        if self.ocr_preset is OcrPreset.FAST:
            return {"pdf_dpi": 150, "max_side_len": 1600}
        if self.ocr_preset is OcrPreset.ACCURATE:
            return {"pdf_dpi": 300, "max_side_len": 4096}
        if self.ocr_preset is OcrPreset.BALANCED:
            return {"pdf_dpi": 200, "max_side_len": 2000}
        return {"pdf_dpi": self.pdf_dpi, "max_side_len": self.max_side_len}
