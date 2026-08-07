from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import threading
from html.parser import HTMLParser
from pathlib import Path

from .runtime import find_soffice


LOGGER = logging.getLogger(__name__)
_LIBREOFFICE_LOCK = threading.Lock()


class LibreOfficeError(RuntimeError):
    pass


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style"}:
            self._hidden_depth += 1
        elif tag.lower() in {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")
        elif tag.lower() in {"td", "th"}:
            self.parts.append("\t")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._hidden_depth:
            self._hidden_depth -= 1
        elif tag.lower() in {"p", "div", "tr", "li", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            self.parts.append(data)

    @property
    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.parts).splitlines()]
        return "\n".join(line for line in lines if line).strip()


def _file_uri(path: Path) -> str:
    return path.resolve().as_uri()


def _run_conversion(source: Path, target_format: str, output_suffix: str, timeout: int) -> bytes:
    soffice = find_soffice()
    if not soffice:
        raise LibreOfficeError("未找到 LibreOffice/soffice。")
    with tempfile.TemporaryDirectory(prefix="document_ocr_lo_") as temporary:
        root = Path(temporary)
        profile = root / "profile"
        output = root / "output"
        profile.mkdir()
        output.mkdir()
        local_source = root / f"input{source.suffix.lower()}"
        local_source.write_bytes(source.read_bytes())
        command = [
            str(soffice),
            "--headless",
            "--nologo",
            "--nodefault",
            "--norestore",
            f"-env:UserInstallation={_file_uri(profile)}",
            "--convert-to",
            target_format,
            "--outdir",
            str(output),
            str(local_source),
        ]
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        environment = os.environ.copy()
        if os.name != "nt":
            # The portable LibreOffice build must not probe an X11/Wayland
            # display when the OCR client is used from a headless Kylin
            # session. Keep its per-run state inside the temporary directory
            # as well, so conversion remains isolated and fully offline.
            home = root / "home"
            config = root / "config"
            cache = root / "cache"
            home.mkdir()
            config.mkdir()
            cache.mkdir()
            environment.setdefault("SAL_USE_VCLPLUGIN", "svp")
            environment["HOME"] = str(home)
            environment["XDG_CONFIG_HOME"] = str(config)
            environment["XDG_CACHE_HOME"] = str(cache)
        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
                creationflags=creationflags,
                env=environment,
            )
        except subprocess.TimeoutExpired as exc:
            raise LibreOfficeError(f"LibreOffice 转换超过 {timeout} 秒。") from exc
        if completed.returncode != 0:
            error = completed.stderr.decode("utf-8", errors="replace").strip()
            raise LibreOfficeError(f"LibreOffice 转换失败（{completed.returncode}）：{error}")
        candidates = sorted(output.glob(f"*{output_suffix}"))
        if not candidates:
            detail = completed.stdout.decode("utf-8", errors="replace").strip()
            raise LibreOfficeError(f"LibreOffice 未生成 {output_suffix} 文件：{detail}")
        return candidates[0].read_bytes()


def convert_word(source: Path, timeout: int = 180) -> tuple[str, str | None]:
    """Return UTF-8-ish plain text and optional HTML from DOC/DOCX/WPS."""
    with _LIBREOFFICE_LOCK:
        raw_text = _run_conversion(source, "txt:Text", ".txt", timeout)
        html_text: str | None = None
        try:
            raw_html = _run_conversion(source, "html:HTML", ".html", timeout)
            html_text = raw_html.decode("utf-8", errors="replace")
        except LibreOfficeError as exc:
            LOGGER.warning("HTML conversion failed for %s: %s", source, exc)

    decoded = ""
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            decoded = raw_text.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if not decoded:
        decoded = raw_text.decode("utf-8", errors="replace")
    decoded = decoded.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not decoded and html_text:
        parser = _VisibleTextParser()
        parser.feed(html_text)
        decoded = parser.text
    return decoded, html_text

