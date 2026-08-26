from __future__ import annotations

import os
import json
import threading
from dataclasses import dataclass
from pathlib import Path

from ..qt import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QImage,
    QPainter,
    QPen,
    QTextCursor,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QRectF,
    QThread,
    Qt,
    Signal,
    Slot,
    event_position,
    point_from_event,
)

from ..inputs import collect_passthrough_files, expand_inputs, unsupported_reason
from ..edition import is_full_edition
from ..models import (
    InputItem,
    LayoutMode,
    OcrBlock,
    OcrPreset,
    OutputMode,
    PageOrientation,
    PassthroughFile,
    PdfMode,
    ProcessingOptions,
    TaskRecord,
    TaskState,
)
from ..outputs import copy_passthrough_files
from ..pipeline import ProcessingPipeline, SavedResult
from ..settings import AppSettings, SettingsStore


@dataclass
class PasswordRequest:
    path: Path
    event: threading.Event
    password: str | None = None


class OcrPreviewWidget(QWidget):
    """Page preview with clickable OCR boxes in original-page coordinates."""

    block_selected = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(230)
        self.setCursor(Qt.CrossCursor)
        self._image = QImage()
        self._blocks: list[tuple[int, OcrBlock]] = []
        self._selected = -1
        self._threshold = 0.5
        self._target = QRectF()

    def set_record(
        self, record: TaskRecord | None, page_index: int = 0, threshold: float = 0.5
    ) -> None:
        self._image = QImage()
        self._blocks = []
        self._selected = -1
        self._threshold = threshold
        if record is None:
            self.update()
            return
        source = record.item.source_path
        if record.item.kind.value == "image":
            self._image = QImage(str(source))
        elif record.item.kind.value == "pdf":
            try:
                import fitz

                document = fitz.open(source)
                try:
                    page = document.load_page(page_index)
                    dpi = int(record.metadata.get("pdf_dpi") or 200)
                    pixmap = page.get_pixmap(dpi=dpi, alpha=False, colorspace=fitz.csRGB)
                    self._image = QImage(
                        pixmap.samples,
                        pixmap.width,
                        pixmap.height,
                        pixmap.stride,
                        QImage.Format_RGB888,
                    ).copy()
                finally:
                    document.close()
            except Exception:
                self._image = QImage()
        self._blocks = [
            (index, block)
            for index, block in enumerate(record.blocks)
            if block.page_index == page_index
        ]
        self.update()

    @Slot(int)
    def select_block(self, index: int) -> None:
        self._selected = index
        self.update()

    def _image_target(self) -> QRectF:
        if self._image.isNull():
            return QRectF()
        available = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        scale = min(
            available.width() / max(1, self._image.width()),
            available.height() / max(1, self._image.height()),
        )
        width = self._image.width() * scale
        height = self._image.height() * scale
        return QRectF(
            available.center().x() - width / 2,
            available.center().y() - height / 2,
            width,
            height,
        )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().base())
        self._target = self._image_target()
        if self._image.isNull():
            painter.setPen(self.palette().placeholderText().color())
            painter.drawText(self.rect(), Qt.AlignCenter, "暂无可预览页面")
            return
        painter.drawImage(self._target, self._image)
        scale_x = self._target.width() / max(1, self._image.width())
        scale_y = self._target.height() / max(1, self._image.height())
        for index, block in self._blocks:
            x1, y1, x2, y2 = block.bounds
            rect = QRectF(
                self._target.left() + x1 * scale_x,
                self._target.top() + y1 * scale_y,
                max(1.0, (x2 - x1) * scale_x),
                max(1.0, (y2 - y1) * scale_y),
            )
            if index == self._selected:
                color, width = QColor("#ffb000"), 3
            elif block.score < self._threshold:
                color, width = QColor("#e44747"), 2
            else:
                color, width = QColor("#3478f6"), 1
            painter.setPen(QPen(color, width))
            painter.drawRect(rect)

    def mousePressEvent(self, event) -> None:
        position = event_position(event)
        if self._image.isNull() or not self._target.contains(position):
            return super().mousePressEvent(event)
        scale_x = self._image.width() / max(1.0, self._target.width())
        scale_y = self._image.height() / max(1.0, self._target.height())
        x = (position.x() - self._target.left()) * scale_x
        y = (position.y() - self._target.top()) * scale_y
        candidates: list[tuple[float, int]] = []
        for index, block in self._blocks:
            x1, y1, x2, y2 = block.bounds
            if x1 <= x <= x2 and y1 <= y <= y2:
                candidates.append(((x2 - x1) * (y2 - y1), index))
        if candidates:
            _, index = min(candidates)
            self._selected = index
            self.block_selected.emit(index)
            self.update()
        event.accept()


class DropZone(QFrame):
    paths_dropped = Signal(list)
    clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName("添加文件")
        self.setToolTip("点击添加文件，也可以将文件、文件夹或压缩包拖到这里")
        self.setMinimumHeight(128)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(6)
        icon = QLabel("＋")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 30px; color: #3478F6; font-weight: 300;")
        title = QLabel("拖入文件、文件夹或压缩包")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 17px; font-weight: 650;")
        supported = "图片、PDF"
        if is_full_edition():
            supported += "、DOC/DOCX/WPS"
        subtitle = QLabel(f"支持{supported}、ZIP/RAR/7Z/TAR/TAR.GZ/TGZ")
        subtitle.setObjectName("Muted")
        subtitle.setAlignment(Qt.AlignCenter)
        for label in (icon, title, subtitle):
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(icon)
        layout.addWidget(title)
        layout.addWidget(subtitle)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("dragActive", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event) -> None:
        self.setProperty("dragActive", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setProperty("dragActive", False)
        self.style().unpolish(self)
        self.style().polish(self)
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.paths_dropped.emit(paths)
        event.acceptProposedAction()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(
            point_from_event(event)
        ):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class BatchWorker(QThread):
    task_started = Signal(int)
    task_progress = Signal(int, int, str)
    task_completed = Signal(int, object)
    task_failed = Signal(int, str)
    password_requested = Signal(object)
    batch_finished = Signal()

    def __init__(
        self,
        records: list[TaskRecord],
        options: ProcessingOptions,
        passthrough_files: list[PassthroughFile] | None = None,
    ) -> None:
        super().__init__()
        self.records = records
        self.options = options
        self.passthrough_files = passthrough_files or []
        self.passthrough_outputs: list[Path] = []
        self.passthrough_error = ""
        self.cancelled = threading.Event()
        self.resume_event = threading.Event()
        self.resume_event.set()
        self.pipeline = ProcessingPipeline()

    def pause(self) -> None:
        self.resume_event.clear()

    def resume(self) -> None:
        self.resume_event.set()

    def cancel(self) -> None:
        self.cancelled.set()
        self.resume_event.set()

    def _wait_if_paused(self) -> None:
        while not self.resume_event.wait(0.15):
            if self.cancelled.is_set():
                raise InterruptedError("任务已取消")

    def _password(self, path: Path) -> str | None:
        request = PasswordRequest(path, threading.Event())
        self.password_requested.emit(request)
        while not request.event.wait(0.1):
            if self.cancelled.is_set():
                return None
        return request.password

    def run(self) -> None:
        try:
            for row, record in enumerate(self.records):
                if record.state not in {TaskState.PENDING, TaskState.FAILED, TaskState.CANCELLED}:
                    continue
                if self.cancelled.is_set():
                    break
                try:
                    self._wait_if_paused()
                    self.task_started.emit(row)

                    def progress(value: int, message: str) -> None:
                        self._wait_if_paused()
                        if self.cancelled.is_set():
                            raise InterruptedError("任务已取消")
                        self.task_progress.emit(row, value, message)

                    results = self.pipeline.process_item(
                        record.item,
                        self.options,
                        progress=progress,
                        cancelled=self.cancelled,
                        password_provider=self._password,
                    )
                    self.task_completed.emit(row, results)
                except InterruptedError:
                    self.task_failed.emit(row, "任务已取消")
                    break
                except Exception as exc:
                    self.task_failed.emit(row, str(exc))
            if not self.cancelled.is_set():
                try:
                    self.passthrough_outputs = copy_passthrough_files(
                        self.passthrough_files, self.options
                    )
                except Exception as exc:
                    self.passthrough_error = str(exc)
        finally:
            self.batch_finished.emit()


class BatchPage(QWidget):
    settings_changed = Signal(object)

    def __init__(self, settings: AppSettings, store: SettingsStore) -> None:
        super().__init__()
        self.settings = settings
        self.store = store
        self.records: list[TaskRecord] = []
        self.passthrough_files: dict[str, PassthroughFile] = {}
        self.worker: BatchWorker | None = None
        self._build_ui()

    @staticmethod
    def _confidence_spin(value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 1.0)
        spin.setDecimals(2)
        spin.setSingleStep(0.05)
        spin.setValue(value)
        return spin

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)
        title = QLabel("批量识别")
        title.setObjectName("PageTitle")
        subtitle = QLabel("拖入资料后统一识别，结果按来源层级保存为 TXT 和 Markdown")
        subtitle.setObjectName("Muted")
        root.addWidget(title)
        root.addWidget(subtitle)

        self.drop_zone = DropZone()
        self.drop_zone.paths_dropped.connect(self.add_paths)
        self.drop_zone.clicked.connect(self.choose_files)
        root.addWidget(self.drop_zone)

        import_row = QHBoxLayout()
        add_files = QPushButton("添加文件")
        add_folder = QPushButton("添加文件夹")
        clear_button = QPushButton("清空列表")
        add_files.clicked.connect(self.choose_files)
        add_folder.clicked.connect(self.choose_folder)
        clear_button.clicked.connect(self.clear_records)
        import_row.addWidget(add_files)
        import_row.addWidget(add_folder)
        import_row.addStretch()
        import_row.addWidget(clear_button)
        root.addLayout(import_row)

        splitter = QSplitter(Qt.Horizontal)
        table_card = QFrame()
        table_card.setObjectName("Card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["文件", "类型", "状态", "进度", "输出"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(1, 64)
        self.table.setColumnWidth(2, 82)
        self.table.setColumnWidth(3, 116)
        self.table.itemSelectionChanged.connect(self.show_selected_result)
        table_layout.addWidget(self.table)

        inspector = QFrame()
        inspector.setObjectName("Inspector")
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.setContentsMargins(16, 16, 16, 16)
        inspector_header = QHBoxLayout()
        inspector_title = QLabel("识别审校")
        inspector_title.setStyleSheet("font-size: 16px; font-weight: 650;")
        self.page_spin = QSpinBox()
        self.page_spin.setPrefix("第 ")
        self.page_spin.setSuffix(" 页")
        self.page_spin.setRange(1, 1)
        self.page_spin.valueChanged.connect(self._show_preview_page)
        inspector_header.addWidget(inspector_title)
        inspector_header.addStretch()
        inspector_header.addWidget(self.page_spin)
        self.preview = OcrPreviewWidget()
        self.preview.block_selected.connect(self.select_result_block)
        self.result_tabs = QTabWidget()
        self.result_editor = QPlainTextEdit()
        self.result_editor.setPlaceholderText("选择已完成任务后可查看和编辑文本")
        self.raw_editor = QPlainTextEdit()
        self.raw_editor.setReadOnly(True)
        self.markdown_editor = QPlainTextEdit()
        self.info_editor = QPlainTextEdit()
        self.info_editor.setReadOnly(True)
        self.result_tabs.addTab(self.result_editor, "整理文本")
        self.result_tabs.addTab(self.raw_editor, "原始文本")
        self.result_tabs.addTab(self.markdown_editor, "Markdown")
        self.result_tabs.addTab(self.info_editor, "识别信息")
        edit_row = QHBoxLayout()
        save_edit = QPushButton("保存文本修改")
        save_edit.clicked.connect(self.save_text_edit)
        copy_edit = QPushButton("复制")
        copy_edit.clicked.connect(self.copy_active_result)
        rerun = QPushButton("重新识别")
        rerun.clicked.connect(self.rerecognize_selected)
        edit_row.addWidget(copy_edit)
        edit_row.addStretch()
        edit_row.addWidget(rerun)
        edit_row.addWidget(save_edit)
        inspector_layout.addLayout(inspector_header)
        inspector_layout.addWidget(self.preview, 2)
        inspector_layout.addWidget(self.result_tabs, 3)
        inspector_layout.addLayout(edit_row)
        splitter.addWidget(table_card)
        splitter.addWidget(inspector)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        options_card = QFrame()
        options_card.setObjectName("SettingsCard")
        options_layout = QVBoxLayout(options_card)
        options_layout.setContentsMargins(14, 10, 14, 10)
        options_layout.setSpacing(8)
        output_row = QHBoxLayout()
        output_row.setSpacing(8)
        output_label = QLabel("输出位置")
        output_label.setStyleSheet("font-weight: 600;")
        self.output_mode = QComboBox()
        self.output_mode.addItem("新建批次目录", OutputMode.NEW_BATCH_DIRECTORY.value)
        self.output_mode.addItem("源文件旁边", OutputMode.ALONGSIDE_SOURCE.value)
        self.output_mode.setCurrentIndex(0 if self.settings.output_mode == OutputMode.NEW_BATCH_DIRECTORY.value else 1)
        self.output_path = QLineEdit(self.settings.output_parent)
        choose_output = QPushButton("选择输出目录")
        choose_output.clicked.connect(self.choose_output_directory)
        self.pdf_mode = QComboBox()
        self.pdf_mode.addItem("PDF 自动判断", PdfMode.AUTO.value)
        self.pdf_mode.addItem("PDF 强制 OCR", PdfMode.FORCE_OCR.value)
        self.pdf_mode.addItem("PDF 仅提取", PdfMode.TEXT_ONLY.value)
        pdf_index = max(0, self.pdf_mode.findData(self.settings.pdf_mode))
        self.pdf_mode.setCurrentIndex(pdf_index)
        self.table_detection = QCheckBox("自动识别表格")
        self.table_detection.setChecked(self.settings.table_detection)
        self.searchable_pdf = QCheckBox("可搜索 PDF")
        self.searchable_pdf.setChecked(self.settings.searchable_pdf)
        self.ocr_preset = QComboBox()
        self.ocr_preset.addItem("快速", OcrPreset.FAST.value)
        self.ocr_preset.addItem("均衡", OcrPreset.BALANCED.value)
        self.ocr_preset.addItem("精度优先", OcrPreset.ACCURATE.value)
        self.ocr_preset.addItem("自定义", OcrPreset.CUSTOM.value)
        self.ocr_preset.setCurrentIndex(max(0, self.ocr_preset.findData(self.settings.ocr_preset)))
        self.page_orientation = QComboBox()
        for label, value in (
            ("方向自动", PageOrientation.AUTO.value),
            ("方向关闭", PageOrientation.OFF.value),
            ("固定 0°", PageOrientation.ROTATE_0.value),
            ("固定 90°", PageOrientation.ROTATE_90.value),
            ("固定 180°", PageOrientation.ROTATE_180.value),
            ("固定 270°", PageOrientation.ROTATE_270.value),
        ):
            self.page_orientation.addItem(label, value)
        self.page_orientation.setCurrentIndex(
            max(0, self.page_orientation.findData(self.settings.page_orientation))
        )
        self.textline_orientation = QCheckBox("文本行 0°/180°")
        self.textline_orientation.setChecked(self.settings.textline_orientation)
        self.layout_mode = QComboBox()
        for label, value in (
            ("多栏自然段", LayoutMode.MULTI_PARAGRAPH.value),
            ("多栏逐行", LayoutMode.MULTI_LINES.value),
            ("单栏自然段", LayoutMode.SINGLE_PARAGRAPH.value),
            ("单栏逐行", LayoutMode.SINGLE_LINES.value),
            ("保留缩进", LayoutMode.CODE.value),
            ("原始结果", LayoutMode.RAW.value),
        ):
            self.layout_mode.addItem(label, value)
        self.layout_mode.setCurrentIndex(
            max(0, self.layout_mode.findData(self.settings.layout_mode))
        )
        self.page_range = QLineEdit(self.settings.page_range)
        self.page_range.setPlaceholderText("PDF 页码：1-3,5")
        self.page_range.setMaximumWidth(150)
        self.copy_unconverted_files = QCheckBox("复制未转换文件")
        self.copy_unconverted_files.setChecked(self.settings.copy_unconverted_files)
        self.copy_unconverted_files.setToolTip(
            "默认关闭。开启后，在新建批次目录中原样保留目录和压缩包内未转换的文件，"
            "例如 TXT、JSON、XLSX、PPT 等。"
        )
        self.output_mode.currentIndexChanged.connect(self._update_copy_option_state)
        output_row.addWidget(output_label)
        output_row.addWidget(self.output_mode)
        output_row.addWidget(self.output_path, 1)
        output_row.addWidget(choose_output)
        recognition_row = QHBoxLayout()
        recognition_row.setSpacing(14)
        recognition_label = QLabel("识别选项")
        recognition_label.setStyleSheet("font-weight: 600;")
        recognition_row.addWidget(recognition_label)
        recognition_row.addWidget(self.pdf_mode)
        recognition_row.addWidget(self.ocr_preset)
        recognition_row.addWidget(self.page_orientation)
        recognition_row.addWidget(self.layout_mode)
        recognition_row.addWidget(self.table_detection)
        recognition_row.addWidget(self.searchable_pdf)
        recognition_row.addStretch()
        detail_row = QHBoxLayout()
        detail_row.setSpacing(12)
        detail_row.addWidget(QLabel("范围与方向"))
        detail_row.addWidget(self.page_range)
        detail_row.addWidget(self.textline_orientation)
        detail_row.addWidget(self.copy_unconverted_files)
        self.advanced_button = QPushButton("高级设置…")
        self.advanced_button.setCheckable(True)
        detail_row.addStretch()
        detail_row.addWidget(self.advanced_button)
        options_layout.addLayout(output_row)
        options_layout.addLayout(recognition_row)
        options_layout.addLayout(detail_row)

        self.advanced_frame = QFrame()
        advanced_layout = QVBoxLayout(self.advanced_frame)
        advanced_layout.setContentsMargins(0, 6, 0, 0)
        advanced_row = QHBoxLayout()
        self.pdf_dpi = QSpinBox()
        self.pdf_dpi.setRange(72, 600)
        self.pdf_dpi.setValue(self.settings.pdf_dpi)
        self.max_side_len = QSpinBox()
        self.max_side_len.setRange(512, 8192)
        self.max_side_len.setValue(self.settings.max_side_len)
        self.det_limit_side_len = QSpinBox()
        self.det_limit_side_len.setRange(320, 4096)
        self.det_limit_side_len.setValue(self.settings.det_limit_side_len)
        self.det_thresh = self._confidence_spin(self.settings.det_thresh)
        self.det_box_thresh = self._confidence_spin(self.settings.det_box_thresh)
        self.det_unclip_ratio = QDoubleSpinBox()
        self.det_unclip_ratio.setRange(1.0, 3.0)
        self.det_unclip_ratio.setSingleStep(0.1)
        self.det_unclip_ratio.setValue(self.settings.det_unclip_ratio)
        self.text_score = self._confidence_spin(self.settings.text_score)
        self.rec_batch_size = QSpinBox()
        self.rec_batch_size.setRange(1, 64)
        self.rec_batch_size.setValue(self.settings.rec_batch_size)
        self.cpu_threads = QSpinBox()
        self.cpu_threads.setRange(0, 128)
        self.cpu_threads.setSpecialValueText("自动")
        self.cpu_threads.setValue(self.settings.cpu_threads)
        for label, widget in (
            ("PDF DPI", self.pdf_dpi),
            ("图像长边", self.max_side_len),
            ("检测边长", self.det_limit_side_len),
            ("检测阈值", self.det_thresh),
            ("框阈值", self.det_box_thresh),
            ("框扩张", self.det_unclip_ratio),
            ("输出置信度", self.text_score),
            ("识别批次", self.rec_batch_size),
            ("CPU线程", self.cpu_threads),
        ):
            group = QVBoxLayout()
            caption = QLabel(label)
            caption.setObjectName("Muted")
            group.addWidget(caption)
            group.addWidget(widget)
            advanced_row.addLayout(group)
        advanced_layout.addLayout(advanced_row)
        self.advanced_frame.setVisible(False)
        self.advanced_button.toggled.connect(self.advanced_frame.setVisible)
        for widget in (
            self.pdf_dpi,
            self.max_side_len,
            self.det_limit_side_len,
            self.det_thresh,
            self.det_box_thresh,
            self.det_unclip_ratio,
            self.text_score,
            self.rec_batch_size,
            self.cpu_threads,
        ):
            widget.valueChanged.connect(lambda _value: self._mark_custom_preset())
        options_layout.addWidget(self.advanced_frame)
        root.addWidget(options_card)

        action_row = QHBoxLayout()
        self.status_label = QLabel("准备就绪")
        self.status_label.setObjectName("Muted")
        self.start_button = QPushButton("开始识别")
        self.start_button.setProperty("primary", True)
        self.pause_button = QPushButton("暂停")
        self.stop_button = QPushButton("停止")
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_processing)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.stop_button.clicked.connect(self.stop_processing)
        action_row.addWidget(self.status_label, 1)
        action_row.addWidget(self.pause_button)
        action_row.addWidget(self.stop_button)
        action_row.addWidget(self.start_button)
        root.addLayout(action_row)
        self._update_copy_option_state()

    @Slot()
    def _mark_custom_preset(self) -> None:
        index = self.ocr_preset.findData(OcrPreset.CUSTOM.value)
        if index >= 0:
            self.ocr_preset.setCurrentIndex(index)

    @Slot()
    def choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "添加识别文件")
        if paths:
            self.add_paths(paths)

    @Slot()
    def choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "添加文件夹")
        if path:
            self.add_paths([path])

    @Slot(list)
    def add_paths(self, paths: list[str]) -> None:
        items, unsupported = expand_inputs(paths)
        passthrough_candidates = collect_passthrough_files(paths, unsupported)
        for passthrough in passthrough_candidates:
            try:
                resolved = passthrough.source_path.resolve()
            except OSError:
                resolved = passthrough.source_path.absolute()
            self.passthrough_files[os.path.normcase(str(resolved))] = passthrough
        existing = {
            os.path.normcase(str(record.item.source_path.resolve())) for record in self.records
        }
        added = 0
        for item in items:
            key = os.path.normcase(str(item.source_path.resolve()))
            if key in existing:
                continue
            existing.add(key)
            added += 1
            self.records.append(TaskRecord(item))
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(item.source_path.name))
            self.table.item(row, 0).setToolTip(item.display_path)
            self.table.setItem(row, 1, QTableWidgetItem(item.kind.value.upper()))
            self.table.setItem(row, 2, QTableWidgetItem(TaskState.PENDING.value))
            progress = QProgressBar()
            progress.setRange(0, 100)
            progress.setValue(0)
            self.table.setCellWidget(row, 3, progress)
            self.table.setItem(row, 4, QTableWidgetItem("—"))
        copyable = len(passthrough_candidates)
        details = f"，发现 {copyable} 个可原样复制文件" if copyable else ""
        skipped = len(unsupported) - copyable
        if skipped:
            reasons = {unsupported_reason(path) for path in unsupported}
            if any("OCR版" in reason for reason in reasons):
                details += "；OCR版不支持 Word/WPS，请下载完整版"
            else:
                details += f"，跳过 {skipped} 个不支持项目"
        self.status_label.setText(f"已添加 {added} 个任务{details}")

    def _options(self) -> ProcessingOptions:
        self.settings.output_mode = str(self.output_mode.currentData())
        self.settings.output_parent = self.output_path.text().strip()
        self.settings.pdf_mode = str(self.pdf_mode.currentData())
        self.settings.table_detection = self.table_detection.isChecked()
        self.settings.searchable_pdf = self.searchable_pdf.isChecked()
        self.settings.copy_unconverted_files = self.copy_unconverted_files.isChecked()
        self.settings.ocr_preset = str(self.ocr_preset.currentData())
        self.settings.page_orientation = str(self.page_orientation.currentData())
        self.settings.textline_orientation = self.textline_orientation.isChecked()
        self.settings.layout_mode = str(self.layout_mode.currentData())
        self.settings.page_range = self.page_range.text().strip()
        self.settings.pdf_dpi = self.pdf_dpi.value()
        self.settings.max_side_len = self.max_side_len.value()
        self.settings.det_limit_side_len = self.det_limit_side_len.value()
        self.settings.det_thresh = self.det_thresh.value()
        self.settings.det_box_thresh = self.det_box_thresh.value()
        self.settings.det_unclip_ratio = self.det_unclip_ratio.value()
        self.settings.text_score = self.text_score.value()
        self.settings.rec_batch_size = self.rec_batch_size.value()
        self.settings.cpu_threads = self.cpu_threads.value()
        self.store.save(self.settings)
        self.settings_changed.emit(self.settings)
        return self.settings.processing_options()

    @Slot()
    def start_processing(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        options = self._options()
        can_copy_only = bool(
            self.passthrough_files
            and options.output_mode is OutputMode.NEW_BATCH_DIRECTORY
            and options.copy_unconverted_files
        )
        if not self.records and not can_copy_only:
            QMessageBox.information(self, "没有任务", "请先拖入或添加需要识别的文件。")
            return
        for record in self.records:
            if record.state in {TaskState.FAILED, TaskState.CANCELLED}:
                record.state = TaskState.PENDING
        self.worker = BatchWorker(
            self.records,
            options,
            list(self.passthrough_files.values()),
        )
        self.worker.task_started.connect(self.on_task_started)
        self.worker.task_progress.connect(self.on_task_progress)
        self.worker.task_completed.connect(self.on_task_completed)
        self.worker.task_failed.connect(self.on_task_failed)
        self.worker.password_requested.connect(self.on_password_requested)
        self.worker.batch_finished.connect(self.on_batch_finished)
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        self.worker.start()

    @Slot(int)
    def on_task_started(self, row: int) -> None:
        self.records[row].state = TaskState.RUNNING
        self.table.item(row, 2).setText(TaskState.RUNNING.value)
        self.status_label.setText(f"正在处理：{self.records[row].item.display_path}")

    @Slot(int, int, str)
    def on_task_progress(self, row: int, value: int, message: str) -> None:
        self.records[row].progress = value
        self.records[row].message = message
        progress = self.table.cellWidget(row, 3)
        if isinstance(progress, QProgressBar):
            progress.setValue(value)
        self.status_label.setText(message)

    @Slot(int, object)
    def on_task_completed(self, row: int, saved_results: list[SavedResult]) -> None:
        record = self.records[row]
        warnings = [warning for saved in saved_results for warning in saved.result.warnings]
        record.state = TaskState.WARNING if warnings else TaskState.SUCCEEDED
        record.text = "\n\n".join(saved.result.text for saved in saved_results)
        record.markdown = "\n\n".join(saved.result.markdown for saved in saved_results)
        record.raw_text = "\n\n".join(saved.result.raw_text for saved in saved_results)
        record.blocks = [block for saved in saved_results for block in saved.result.blocks]
        if len(saved_results) == 1:
            record.metadata = dict(saved_results[0].result.metadata)
        else:
            record.metadata = {
                "result_count": len(saved_results),
                "results": [saved.result.metadata for saved in saved_results],
            }
        record.outputs = [path for saved in saved_results for path in saved.outputs]
        record.warnings = warnings
        self.table.item(row, 2).setText(record.state.value)
        self.table.item(row, 4).setText(str(len(record.outputs)) + " 个文件")
        progress = self.table.cellWidget(row, 3)
        if isinstance(progress, QProgressBar):
            progress.setValue(100)
        if self.table.currentRow() < 0:
            self.table.setCurrentCell(row, 0)
            self.table.selectRow(row)
        if self.table.currentRow() == row:
            self._display_record(record)

    @Slot(int, str)
    def on_task_failed(self, row: int, message: str) -> None:
        record = self.records[row]
        record.state = TaskState.CANCELLED if "取消" in message else TaskState.FAILED
        record.message = message
        self.table.item(row, 2).setText(record.state.value)
        self.table.item(row, 4).setText(message)

    @Slot(object)
    def on_password_requested(self, request: PasswordRequest) -> None:
        password, accepted = QInputDialog.getText(
            self,
            "压缩包密码",
            f"请输入 {request.path.name} 的密码：",
            QLineEdit.Password,
        )
        request.password = password if accepted else None
        request.event.set()

    @Slot()
    def on_batch_finished(self) -> None:
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.pause_button.setText("暂停")
        completed = sum(record.state in {TaskState.SUCCEEDED, TaskState.WARNING} for record in self.records)
        failed = sum(record.state is TaskState.FAILED for record in self.records)
        message = f"批次完成：成功 {completed}，失败 {failed}"
        if self.worker and self.worker.passthrough_outputs:
            message += f"，复制未转换文件 {len(self.worker.passthrough_outputs)} 个"
        if self.worker and self.worker.passthrough_error:
            message += f"；未转换文件复制失败：{self.worker.passthrough_error}"
        self.status_label.setText(message)

    @Slot()
    def toggle_pause(self) -> None:
        if not self.worker:
            return
        if self.pause_button.text() == "暂停":
            self.worker.pause()
            self.pause_button.setText("继续")
            self.status_label.setText("将在当前安全步骤结束后暂停")
        else:
            self.worker.resume()
            self.pause_button.setText("暂停")

    @Slot()
    def stop_processing(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.status_label.setText("正在停止…")

    @Slot()
    def clear_records(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        self.records.clear()
        self.passthrough_files.clear()
        self.table.setRowCount(0)
        self.result_editor.clear()
        self.raw_editor.clear()
        self.markdown_editor.clear()
        self.info_editor.clear()
        self.preview.set_record(None)
        self.status_label.setText("准备就绪")

    @Slot()
    def show_selected_result(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.records):
            self._display_record(self.records[row])
        else:
            self.preview.set_record(None)

    def _display_record(self, record: TaskRecord) -> None:
        self.result_editor.setPlainText(record.text)
        self.raw_editor.setPlainText(record.raw_text)
        self.markdown_editor.setPlainText(record.markdown)
        self.info_editor.setPlainText(
            json.dumps(record.metadata, ensure_ascii=False, indent=2)
        )
        page_count = int(record.metadata.get("page_count") or 1)
        self.page_spin.blockSignals(True)
        self.page_spin.setRange(1, max(1, page_count))
        processed = record.metadata.get("processed_pages")
        first_page = int(processed[0]) if isinstance(processed, list) and processed else 1
        self.page_spin.setValue(max(1, min(first_page, page_count)))
        self.page_spin.blockSignals(False)
        self.preview.set_record(record, self.page_spin.value() - 1, self.settings.text_score)

    @Slot(int)
    def _show_preview_page(self, page_number: int) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.records):
            self.preview.set_record(
                self.records[row], page_number - 1, self.settings.text_score
            )

    @Slot(int)
    def select_result_block(self, block_index: int) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self.records)):
            return
        blocks = self.records[row].blocks
        if not (0 <= block_index < len(blocks)):
            return
        block = blocks[block_index]
        editor = self.raw_editor
        self.result_tabs.setCurrentWidget(editor)
        text = editor.toPlainText()
        start = text.find(block.text)
        if start >= 0:
            cursor = editor.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(
                start + len(block.text), QTextCursor.KeepAnchor
            )
            editor.setTextCursor(cursor)
            editor.ensureCursorVisible()

    @Slot()
    def copy_active_result(self) -> None:
        widget = self.result_tabs.currentWidget()
        if isinstance(widget, QPlainTextEdit):
            QApplication.clipboard().setText(widget.toPlainText())
            self.status_label.setText("已复制当前结果")

    @Slot()
    def rerecognize_selected(self) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self.records)) or (self.worker and self.worker.isRunning()):
            return
        record = self.records[row]
        record.state = TaskState.PENDING
        record.progress = 0
        self.table.item(row, 2).setText(TaskState.PENDING.value)
        progress = self.table.cellWidget(row, 3)
        if isinstance(progress, QProgressBar):
            progress.setValue(0)
        self.start_processing()

    @Slot()
    def save_text_edit(self) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self.records)):
            return
        record = self.records[row]
        text_outputs = [path for path in record.outputs if path.suffix.lower() == ".txt"]
        if not text_outputs:
            return
        text_outputs[0].write_text(self.result_editor.toPlainText().rstrip() + "\n", encoding="utf-8")
        record.text = self.result_editor.toPlainText()
        markdown_outputs = [path for path in record.outputs if path.suffix.lower() == ".md"]
        if markdown_outputs:
            markdown_outputs[0].write_text(
                self.markdown_editor.toPlainText().rstrip() + "\n", encoding="utf-8"
            )
            record.markdown = self.markdown_editor.toPlainText()
        self.status_label.setText(f"已保存：{text_outputs[0]}")

    @Slot()
    def choose_output_directory(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出父目录", self.output_path.text())
        if path:
            self.output_path.setText(path)

    @Slot()
    def _update_copy_option_state(self) -> None:
        enabled = self.output_mode.currentData() == OutputMode.NEW_BATCH_DIRECTORY.value
        self.copy_unconverted_files.setEnabled(enabled)
        if enabled:
            self.copy_unconverted_files.setToolTip(
                "默认关闭。开启后，在新建批次目录中原样保留目录和压缩包内未转换的文件，"
                "例如 TXT、JSON、XLSX、PPT 等。"
            )
        else:
            self.copy_unconverted_files.setToolTip("仅“新建批次目录”模式支持复制未转换文件。")
    LayoutMode,
    OcrBlock,
    OcrPreset,
    PageOrientation,
