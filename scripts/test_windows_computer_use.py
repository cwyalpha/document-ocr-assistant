from __future__ import annotations

import argparse
import ctypes
import json
import time
from pathlib import Path

from PIL import Image


def capture_window(hwnd: int, output: Path) -> None:
    import win32gui
    import win32ui

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width, height = right - left, bottom - top
    window_dc = win32gui.GetWindowDC(hwnd)
    source_dc = win32ui.CreateDCFromHandle(window_dc)
    memory_dc = source_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    try:
        bitmap.CreateCompatibleBitmap(source_dc, width, height)
        memory_dc.SelectObject(bitmap)
        rendered = ctypes.windll.user32.PrintWindow(hwnd, memory_dc.GetSafeHdc(), 2)
        if not rendered:
            raise RuntimeError("PrintWindow 无法捕获客户端窗口。")
        image = Image.frombuffer(
            "RGB",
            (width, height),
            bitmap.GetBitmapBits(True),
            "raw",
            "BGRX",
            0,
            1,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output)
    finally:
        win32gui.DeleteObject(bitmap.GetHandle())
        memory_dc.DeleteDC()
        source_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, window_dc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Windows 冻结客户端 UI Automation 端到端测试")
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()

    try:
        from pywinauto import Application
    except ImportError as exc:
        raise RuntimeError("请先安装测试依赖：pip install pywinauto==0.6.9") from exc

    exe = args.exe.resolve(strict=True)
    input_path = args.input.resolve(strict=True)
    output_root = args.output.resolve()
    evidence = args.evidence.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)

    report: dict[str, object] = {
        "exe": str(exe),
        "input": str(input_path),
        "actions": [],
        "screenshots": [],
    }
    import psutil

    existing_pids = {
        process.pid
        for process in psutil.process_iter(["exe"])
        if process.info.get("exe")
        and Path(str(process.info["exe"])).resolve() == exe
    }
    application = Application(backend="uia").start(str(exe))
    try:
        window = application.window(title="文档OCR助手")
        window.wait("visible enabled", timeout=30)
        time.sleep(1)
        control_count = len(window.descendants())
        if control_count < 40:
            raise AssertionError(f"主界面可访问控件过少：{control_count}")
        report["control_count"] = control_count

        initial = evidence / "01-main-window.png"
        capture_window(window.handle, initial)
        report["screenshots"].append(str(initial))

        settings_nav = window.child_window(title="设置", control_type="CheckBox").wrapper_object()
        settings_nav.invoke()
        office_text = window.child_window(
            title_re=".*Microsoft Word.*WPS Office.*", control_type="Text"
        )
        office_text.wait("visible", timeout=10)
        report["actions"].append("打开设置页并确认 Windows Office 引擎")
        settings_shot = evidence / "02-settings.png"
        capture_window(window.handle, settings_shot)
        report["screenshots"].append(str(settings_shot))

        batch_nav = window.child_window(title="批量识别", control_type="CheckBox").wrapper_object()
        batch_nav.invoke()
        add_button = window.child_window(title="添加文件", control_type="Button")
        add_button.wait("visible enabled", timeout=10)

        output_edit = window.child_window(
            auto_id="QApplication.MainWindow.QWidget.QStackedWidget.BatchPage.SettingsCard.QLineEdit",
            control_type="Edit",
        ).wrapper_object()
        output_edit.set_edit_text(str(output_root))
        if Path(output_edit.get_value()) != output_root:
            raise AssertionError("输出目录没有通过界面控件写入。")

        add_button.wrapper_object().invoke()
        file_dialog = window.child_window(title="添加识别文件", control_type="Window")
        file_dialog.wait("visible enabled", timeout=10)
        filename_edit = file_dialog.child_window(auto_id="1148", control_type="Edit").wrapper_object()
        filename_edit.set_edit_text(str(input_path))
        file_dialog.child_window(auto_id="1", control_type="SplitButton").wrapper_object().invoke()
        file_dialog.wait_not("exists", timeout=20)

        input_cell = window.child_window(title=input_path.name, control_type="DataItem")
        input_cell.wait("visible", timeout=10)
        report["actions"].append("通过系统文件对话框添加 PDF")

        table_checkbox = window.child_window(title="自动识别表格", control_type="CheckBox").wrapper_object()
        searchable_checkbox = window.child_window(title="可搜索 PDF", control_type="CheckBox").wrapper_object()
        if table_checkbox.get_toggle_state() == 0:
            table_checkbox.toggle()
        if searchable_checkbox.get_toggle_state() == 0:
            searchable_checkbox.toggle()
        if table_checkbox.get_toggle_state() == 0 or searchable_checkbox.get_toggle_state() == 0:
            raise AssertionError("PDF/表格选项未通过界面成功启用。")

        added_shot = evidence / "03-pdf-added.png"
        capture_window(window.handle, added_shot)
        report["screenshots"].append(str(added_shot))

        start_button = window.child_window(title="开始识别", control_type="Button").wrapper_object()
        if not start_button.is_enabled():
            raise AssertionError("添加 PDF 后开始识别按钮仍不可用。")
        start_button.invoke()
        report["actions"].append("启用表格与可搜索 PDF 后开始识别")

        deadline = time.monotonic() + 180
        final_state = ""
        while time.monotonic() < deadline:
            states = [item.window_text() for item in window.descendants(control_type="DataItem")]
            if "失败" in states:
                raise AssertionError(f"界面任务失败：{states}")
            if "已完成" in states or "有警告" in states:
                final_state = "已完成" if "已完成" in states else "有警告"
                break
            time.sleep(0.5)
        if not final_state:
            raise TimeoutError("界面 OCR 任务在 180 秒内未完成。")
        report["final_state"] = final_state

        time.sleep(1)
        result_editor = window.child_window(
            auto_id=(
                "QApplication.MainWindow.QWidget.QStackedWidget.BatchPage."
                "QSplitter.Inspector.QPlainTextEdit"
            ),
            control_type="Edit",
        ).wrapper_object()
        preview_text = result_editor.get_value().strip()
        if len(preview_text) < 20:
            raise AssertionError("任务完成后识别结果没有自动显示在结果面板。")
        report["result_preview_chars"] = len(preview_text)
        completed_shot = evidence / "04-pdf-completed.png"
        capture_window(window.handle, completed_shot)
        report["screenshots"].append(str(completed_shot))

        outputs = sorted(path for path in output_root.rglob("*") if path.is_file())
        suffixes = {path.suffix.lower() for path in outputs}
        if not {".txt", ".md", ".pdf"}.issubset(suffixes):
            raise AssertionError(f"界面流程输出不完整：{outputs}")
        report["outputs"] = [str(path) for path in outputs]

        history_nav = window.child_window(title="历史记录", control_type="CheckBox").wrapper_object()
        history_nav.invoke()
        window.child_window(title="截图历史", control_type="Text").wait("visible", timeout=10)
        window.child_window(title="清空历史", control_type="Button").wait("visible", timeout=10)
        report["actions"].append("打开截图历史页并确认控件正常")
        history_shot = evidence / "05-history.png"
        capture_window(window.handle, history_shot)
        report["screenshots"].append(str(history_shot))

        report_path = evidence / "computer-use-report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        try:
            application.kill()
        except Exception:
            pass
        for process in psutil.process_iter(["exe"]):
            try:
                if (
                    process.pid not in existing_pids
                    and process.info.get("exe")
                    and Path(str(process.info["exe"])).resolve() == exe
                ):
                    process.kill()
            except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
                pass


if __name__ == "__main__":
    raise SystemExit(main())
