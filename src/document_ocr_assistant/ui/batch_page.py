from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal, Slot
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..inputs import collect_passthrough_files, expand_inputs
from ..models import (
    InputItem,
    OutputMode,
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


class DropZone(QFrame):
    paths_dropped = Signal(list)
    clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("添加文件")
        self.setToolTip("点击添加文件，也可以将文件、文件夹或压缩包拖到这里")
        self.setMinimumHeight(128)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(6)
        icon = QLabel("＋")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 30px; color: #3478F6; font-weight: 300;")
        title = QLabel("拖入文件、文件夹或压缩包")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 17px; font-weight: 650;")
        subtitle = QLabel("支持图片、PDF、DOC/DOCX/WPS、ZIP/RAR/7Z/TAR/TAR.GZ/TGZ")
        subtitle.setObjectName("Muted")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for label in (icon, title, subtitle):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
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
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
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

        splitter = QSplitter(Qt.Orientation.Horizontal)
        table_card = QFrame()
        table_card.setObjectName("Card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["文件", "类型", "状态", "进度", "输出"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
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
        inspector_title = QLabel("识别结果")
        inspector_title.setStyleSheet("font-size: 16px; font-weight: 650;")
        self.result_editor = QPlainTextEdit()
        self.result_editor.setPlaceholderText("选择已完成任务后可查看和编辑文本")
        save_edit = QPushButton("保存文本修改")
        save_edit.clicked.connect(self.save_text_edit)
        inspector_layout.addWidget(inspector_title)
        inspector_layout.addWidget(self.result_editor, 1)
        inspector_layout.addWidget(save_edit)
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
        recognition_row.addWidget(self.table_detection)
        recognition_row.addWidget(self.searchable_pdf)
        recognition_row.addWidget(self.copy_unconverted_files)
        recognition_row.addStretch()
        options_layout.addLayout(output_row)
        options_layout.addLayout(recognition_row)
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
            details += f"，跳过 {skipped} 个不支持项目"
        self.status_label.setText(f"已添加 {added} 个任务{details}")

    def _options(self) -> ProcessingOptions:
        self.settings.output_mode = str(self.output_mode.currentData())
        self.settings.output_parent = self.output_path.text().strip()
        self.settings.pdf_mode = str(self.pdf_mode.currentData())
        self.settings.table_detection = self.table_detection.isChecked()
        self.settings.searchable_pdf = self.searchable_pdf.isChecked()
        self.settings.copy_unconverted_files = self.copy_unconverted_files.isChecked()
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
            self.result_editor.setPlainText(record.text)

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
            QLineEdit.EchoMode.Password,
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
        self.status_label.setText("准备就绪")

    @Slot()
    def show_selected_result(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.records):
            self.result_editor.setPlainText(self.records[row].text)

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
