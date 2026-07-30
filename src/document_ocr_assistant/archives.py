from __future__ import annotations

import os
import shutil
import struct
import sys
import tarfile
import tempfile
import unicodedata
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .inputs import classify_path, compound_suffix
from .models import InputItem, InputKind, PassthroughFile
from .runtime import find_archive_tool


MAX_ARCHIVE_DEPTH = 3
MAX_ARCHIVE_MEMBERS = 10_000
MAX_ARCHIVE_BYTES = 10 * 1024 * 1024 * 1024
PasswordProvider = Callable[[Path], str | None]


class ArchiveError(RuntimeError):
    pass


def _unicode_zip_path(info: zipfile.ZipInfo, raw_name: bytes) -> str | None:
    """Read Info-ZIP's Unicode Path extra field when the UTF-8 flag is absent."""
    offset = 0
    extra = info.extra
    while offset + 4 <= len(extra):
        field_id, size = struct.unpack_from("<HH", extra, offset)
        offset += 4
        payload = extra[offset : offset + size]
        offset += size
        if field_id != 0x7075 or len(payload) < 5 or payload[0] != 1:
            continue
        stored_crc = struct.unpack_from("<I", payload, 1)[0]
        if stored_crc != (zlib.crc32(raw_name) & 0xFFFFFFFF):
            continue
        try:
            return payload[5:].decode("utf-8")
        except UnicodeDecodeError:
            return None
    return None


def _cjk_count(value: str) -> int:
    return sum(
        1
        for character in value
        if "\u3400" <= character <= "\u9fff"
        or "\uf900" <= character <= "\ufaff"
    )


def _decoded_zip_name(info: zipfile.ZipInfo) -> str:
    """Decode ZIP member names consistently on Windows and Linux.

    ZIP files without the UTF-8 flag are specified as CP437, but Chinese
    Windows archivers commonly store raw GBK bytes without declaring the
    encoding. Python therefore exposes mojibake such as ``│┬╬¿...``. Recover
    the original bytes and apply an archive-independent policy so extraction
    behaves the same under Windows UTF-8 mode and Kylin locales.
    """
    original = info.filename
    if info.flag_bits & 0x800:
        return unicodedata.normalize("NFC", original)
    try:
        raw_name = original.encode("cp437")
    except UnicodeEncodeError:
        return unicodedata.normalize("NFC", original)

    unicode_extra = _unicode_zip_path(info, raw_name)
    if unicode_extra is not None:
        return unicodedata.normalize("NFC", unicode_extra)

    forced_encoding = os.environ.get("DOCUMENT_OCR_ZIP_ENCODING", "").strip()
    if forced_encoding:
        try:
            decoded = raw_name.decode(forced_encoding)
        except (LookupError, UnicodeDecodeError) as exc:
            raise ArchiveError(
                f"ZIP 文件名无法按 {forced_encoding} 解码：{original}"
            ) from exc
        return unicodedata.normalize("NFC", decoded)

    # Some tools write UTF-8 bytes but forget bit 11. A strict UTF-8 decode is
    # unambiguous enough to prefer before legacy code pages.
    try:
        utf8_name = raw_name.decode("utf-8")
    except UnicodeDecodeError:
        utf8_name = ""
    if utf8_name and utf8_name != original:
        return unicodedata.normalize("NFC", utf8_name)

    # GB18030 is a strict superset of GBK/CP936. Require at least two CJK
    # characters to avoid changing ordinary Western CP437 file names.
    try:
        chinese_name = raw_name.decode("gb18030")
    except UnicodeDecodeError:
        chinese_name = ""
    if _cjk_count(chinese_name) >= 2:
        return unicodedata.normalize("NFC", chinese_name)
    return unicodedata.normalize("NFC", original)


def _safe_target(root: Path, member_name: str) -> Path:
    normalized = member_name.replace("\\", "/")
    target = root.joinpath(*[part for part in normalized.split("/") if part not in {"", "."}])
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ArchiveError(f"压缩包包含不安全路径：{member_name}") from exc
    return target


def _check_limits(count: int, total_size: int) -> None:
    if count > MAX_ARCHIVE_MEMBERS:
        raise ArchiveError(f"压缩包文件数超过限制（{MAX_ARCHIVE_MEMBERS}）。")
    if total_size > MAX_ARCHIVE_BYTES:
        raise ArchiveError("压缩包解压后总大小超过 10 GiB。")


def _extract_zip(source: Path, target: Path, password_provider: PasswordProvider | None) -> None:
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        _check_limits(len(infos), sum(info.file_size for info in infos))
        encrypted = any(info.flag_bits & 0x1 for info in infos)
        password = password_provider(source) if encrypted and password_provider else None
        if encrypted and not password:
            raise ArchiveError("压缩包已加密，但未提供密码。")
        password_bytes = password.encode("utf-8") if password else None
        for info in infos:
            member_name = _decoded_zip_name(info)
            destination = _safe_target(target, member_name)
            mode = info.external_attr >> 16
            if mode and (mode & 0o170000) == 0o120000:
                continue
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                with archive.open(info, pwd=password_bytes) as source_stream, destination.open("wb") as target_stream:
                    shutil.copyfileobj(source_stream, target_stream)
            except RuntimeError as exc:
                if "password" in str(exc).lower():
                    raise ArchiveError("压缩包密码错误。") from exc
                raise


def _extract_7z(source: Path, target: Path, password_provider: PasswordProvider | None) -> None:
    try:
        import py7zr
    except ImportError as exc:
        raise ArchiveError("未安装 py7zr，无法处理 7Z。") from exc
    password: str | None = None
    try:
        with py7zr.SevenZipFile(source, mode="r") as archive:
            encrypted = bool(
                getattr(archive, "password_protected", False) or archive.needs_password()
            )
    except py7zr.exceptions.PasswordRequired:
        # Header-encrypted 7Z files cannot even be opened far enough to call
        # needs_password(). They still need to trigger the password dialog.
        encrypted = True
    except Exception as exc:
        raise ArchiveError(f"无法读取 7Z：{exc}") from exc
    if encrypted:
        password = password_provider(source) if password_provider else None
        if not password:
            raise ArchiveError("7Z 已加密，但未提供密码。")
    try:
        with py7zr.SevenZipFile(source, mode="r", password=password) as archive:
            names = archive.getnames()
            infos = archive.list()
            unpacked_size = sum(int(info.uncompressed or 0) for info in infos)
            _check_limits(len(names), unpacked_size)
            for name in names:
                _safe_target(target, name)
            archive.extractall(path=target)
    except Exception as exc:
        if "password" in str(exc).lower() or "corrupt" in str(exc).lower():
            raise ArchiveError("7Z 密码错误或文件已损坏。") from exc
        raise ArchiveError(f"7Z 解压失败：{exc}") from exc


def _extract_tar(source: Path, target: Path) -> None:
    with tarfile.open(source, "r:*") as archive:
        members = archive.getmembers()
        _check_limits(len(members), sum(member.size for member in members))
        for member in members:
            destination = _safe_target(target, member.name)
            if member.issym() or member.islnk() or member.isdev():
                continue
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                destination.parent.mkdir(parents=True, exist_ok=True)
                stream = archive.extractfile(member)
                if stream:
                    with stream, destination.open("wb") as target_stream:
                        shutil.copyfileobj(stream, target_stream)


def _extract_rar(source: Path, target: Path, password_provider: PasswordProvider | None) -> None:
    try:
        import rarfile
    except ImportError as exc:
        raise ArchiveError("未安装 rarfile，无法处理 RAR。") from exc
    tool = find_archive_tool(("unrar", "unar", "7zz", "7z"))
    if tool:
        name = tool.name.lower()
        if name.startswith("unrar"):
            rarfile.UNRAR_TOOL = str(tool)
        elif name == "unar":
            rarfile.UNAR_TOOL = str(tool)
        elif name == "7zz":
            rarfile.SEVENZIP2_TOOL = str(tool)
        elif name == "7z":
            rarfile.SEVENZIP_TOOL = str(tool)
        rarfile.tool_setup(force=True)
    elif sys.platform == "darwin" and Path("/usr/bin/tar").is_file():
        # macOS ships libarchive's bsdtar implementation as /usr/bin/tar.
        # It handles common non-encrypted RAR archives without Homebrew.
        rarfile.BSDTAR_TOOL = "/usr/bin/tar"
        rarfile.tool_setup(force=True)
    try:
        with rarfile.RarFile(source) as archive:
            infos = archive.infolist()
            _check_limits(len(infos), sum(info.file_size for info in infos))
            for info in infos:
                _safe_target(target, info.filename)
            needs_password = archive.needs_password()
            password = password_provider(source) if needs_password and password_provider else None
            if needs_password and not password:
                raise ArchiveError("RAR 已加密，但未提供密码。")
            archive.extractall(path=target, pwd=password)
    except ArchiveError:
        raise
    except Exception as exc:
        if "password" in str(exc).lower():
            raise ArchiveError("RAR 密码错误。") from exc
        raise ArchiveError(f"RAR 解压失败：{exc}") from exc


def extract_archive(source: Path, target: Path, password_provider: PasswordProvider | None = None) -> None:
    suffix = compound_suffix(source)
    if suffix == ".zip":
        _extract_zip(source, target, password_provider)
    elif suffix == ".7z":
        _extract_7z(source, target, password_provider)
    elif suffix == ".rar":
        _extract_rar(source, target, password_provider)
    elif suffix in {".tar", ".tar.gz", ".tgz"}:
        _extract_tar(source, target)
    else:
        raise ArchiveError(f"不支持的压缩格式：{suffix}")


@dataclass
class ArchiveSession:
    source: Path
    password_provider: PasswordProvider | None = None
    _temporary: tempfile.TemporaryDirectory[str] | None = None
    unconverted_files: list[PassthroughFile] = field(default_factory=list, init=False)

    def __enter__(self) -> list[InputItem]:
        self.unconverted_files.clear()
        self._temporary = tempfile.TemporaryDirectory(prefix="document_ocr_archive_")
        root = Path(self._temporary.name)
        extracted: list[tuple[Path, Path, int]] = [(self.source, Path(), 0)]
        output_items: list[InputItem] = []
        while extracted:
            archive_path, virtual_parent, depth = extracted.pop(0)
            if depth >= MAX_ARCHIVE_DEPTH:
                continue
            archive_root = root / f"level-{depth}-{len(extracted)}-{archive_path.stem}"
            archive_root.mkdir(parents=True, exist_ok=True)
            extract_archive(archive_path, archive_root, self.password_provider)
            for current_root, directories, files in os.walk(archive_root, followlinks=False):
                directories[:] = [name for name in directories if not (Path(current_root) / name).is_symlink()]
                for name in files:
                    path = Path(current_root) / name
                    if path.is_symlink():
                        continue
                    relative = path.relative_to(archive_root)
                    virtual = virtual_parent / relative
                    kind = classify_path(path)
                    if kind is InputKind.ARCHIVE:
                        extracted.append((path, virtual.with_suffix(""), depth + 1))
                    elif kind is not InputKind.UNSUPPORTED:
                        output_items.append(
                            InputItem(
                                path,
                                kind,
                                root_path=archive_root,
                                virtual_path=virtual,
                                archive_path=self.source,
                            )
                        )
                    else:
                        self.unconverted_files.append(
                            PassthroughFile(
                                path,
                                virtual,
                                archive_path=self.source,
                            )
                        )
        return output_items

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._temporary:
            self._temporary.cleanup()
            self._temporary = None
