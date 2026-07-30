from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import threading
from pathlib import Path


LOGGER = logging.getLogger(__name__)
_OFFICE_LOCK = threading.Lock()
_DUMMY_PASSWORD = "__DOCUMENT_OCR_NO_DIALOG__"


class WindowsOfficeError(RuntimeError):
    pass


def _is_registered(prog_id: str) -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"{prog_id}\CLSID"):
            return True
    except OSError:
        return False


def registered_office_backends() -> list[str]:
    result: list[str] = []
    if _is_registered("Word.Application"):
        result.append("Microsoft Word")
    if _is_registered("KWPS.Application"):
        result.append("WPS Office")
    return result


def _backend_order(source: Path) -> list[tuple[str, str]]:
    requested = os.environ.get("DOCUMENT_OCR_WINDOWS_OFFICE", "auto").strip().lower()
    word = ("Microsoft Word", "Word.Application")
    wps = ("WPS Office", "KWPS.Application")
    if requested == "word":
        values = [word]
    elif requested == "wps":
        values = [wps]
    elif requested == "auto":
        values = [wps, word] if source.suffix.lower() == ".wps" else [word, wps]
    else:
        raise WindowsOfficeError(
            "DOCUMENT_OCR_WINDOWS_OFFICE 仅支持 auto、word 或 wps。"
        )
    registered = [value for value in values if _is_registered(value[1])]
    return registered or values


def _decode_html(contents: bytes) -> str:
    if contents.startswith((b"\xff\xfe", b"\xfe\xff")):
        return contents.decode("utf-16")
    if contents.startswith(b"\xef\xbb\xbf"):
        return contents.decode("utf-8-sig")
    header = contents[:4096].decode("ascii", errors="ignore")
    match = re.search(r"charset\s*=\s*[\"']?([A-Za-z0-9._-]+)", header, re.I)
    encodings = [match.group(1)] if match else []
    encodings.extend(["utf-8", "gb18030", "windows-1252"])
    for encoding in encodings:
        try:
            return contents.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return contents.decode("utf-8", errors="replace")


def _normalize_word_text(value: object) -> str:
    text = str(value or "")
    text = text.replace("\r\x07", "\n").replace("\x07", "")
    text = text.replace("\r", "\n").replace("\v", "\n")
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines).strip()


def _new_application(client, prog_id: str):
    try:
        return client.DispatchEx(prog_id)
    except Exception:
        # Some WPS editions do not expose DispatchEx, but Dispatch still
        # creates a separate automation instance when no active server exists.
        return client.Dispatch(prog_id)


def _open_read_only(application, path: Path):
    try:
        return application.Documents.Open(
            FileName=str(path),
            ConfirmConversions=False,
            ReadOnly=True,
            AddToRecentFiles=False,
            PasswordDocument=_DUMMY_PASSWORD,
            Visible=False,
        )
    except Exception as first_error:
        try:
            # Core positional arguments are supported by both Word and WPS.
            return application.Documents.Open(
                str(path), False, True, False, _DUMMY_PASSWORD
            )
        except Exception:
            raise first_error


def _save_filtered_html(document, target: Path) -> str | None:
    try:
        save = getattr(document, "SaveAs2", None) or document.SaveAs
        save(str(target), 10)  # wdFormatFilteredHTML
        if target.is_file():
            return _decode_html(target.read_bytes())
    except Exception as exc:
        LOGGER.warning("Office HTML export failed: %s", exc)
    return None


def _convert_with_backend(source: Path, display_name: str, prog_id: str) -> tuple[str, str | None]:
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise WindowsOfficeError("Windows 版本缺少 pywin32，无法调用 Word/WPS。") from exc

    pythoncom.CoInitialize()
    application = None
    document = None
    try:
        application = _new_application(win32com.client, prog_id)
        application.Visible = False
        application.DisplayAlerts = 0
        try:
            application.AutomationSecurity = 3  # msoAutomationSecurityForceDisable
        except Exception:
            pass
        document = _open_read_only(application, source)
        text = _normalize_word_text(document.Content.Text)
        html = _save_filtered_html(document, source.with_suffix(".html"))
        if not text and not html:
            raise WindowsOfficeError(f"{display_name} 未返回可读取内容。")
        LOGGER.info("已使用 %s 转换：%s", display_name, source.name)
        return text, html
    except Exception as exc:
        raise WindowsOfficeError(f"{display_name} 转换失败：{exc}") from exc
    finally:
        if document is not None:
            try:
                document.Close(False)
            except Exception:
                pass
        if application is not None:
            try:
                application.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()


def convert_word_windows(source: Path, timeout: int = 180) -> tuple[str, str | None]:
    """Read DOC/DOCX/WPS with installed Microsoft Word or WPS Office.

    ``timeout`` is kept for API symmetry and future process-isolated conversion;
    DisplayAlerts and a dummy password prevent normal modal prompts.
    """
    del timeout
    if os.name != "nt":
        raise WindowsOfficeError("Windows Office COM 只能在 Windows 中运行。")
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    errors: list[str] = []
    with _OFFICE_LOCK, tempfile.TemporaryDirectory(prefix="document_ocr_office_") as temporary:
        local_source = Path(temporary) / f"input{source.suffix.lower()}"
        shutil.copy2(source, local_source)
        for display_name, prog_id in _backend_order(source):
            try:
                return _convert_with_backend(local_source, display_name, prog_id)
            except WindowsOfficeError as exc:
                errors.append(str(exc))
                LOGGER.warning("%s", exc)
    installed = registered_office_backends()
    if not installed:
        raise WindowsOfficeError("未检测到 Microsoft Word 或 WPS Office，无法转换 Office 文档。")
    raise WindowsOfficeError("；".join(errors))

