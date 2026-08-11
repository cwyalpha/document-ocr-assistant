#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from create_release_checksums import asset_names


FORBIDDEN_NAMES = re.compile(
    r"(^|/)(\.env($|\.)|.*\.(pem|p12|pfx|key|log)|settings\.json|"
    r"history.*\.sqlite3?|\.DS_Store|__pycache__|\.pytest_cache)(/|$)",
    re.IGNORECASE,
)
TEST_DOCUMENTS = re.compile(r"(^|/)(tests?|fixtures?)/.*\.(pdf|docx?|wps)$", re.IGNORECASE)
LOCAL_PATH = re.compile(
    rb"(?:/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/|[A-Za-z]:\\Users\\[^\\\r\n]+\\)"
)
SECRET_PATTERNS = (
    re.compile(rb"ghp_[A-Za-z0-9]{20,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
TEXT_SUFFIXES = {
    ".txt", ".md", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".py", ".sh", ".ps1", ".bat", ".iss", ".spec", ".desktop", ".xml",
}


class Audit:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.build_infos: list[dict[str, object]] = []

    def name(self, logical_name: str, *, source: bool = False, edition: str = "") -> None:
        normalized = logical_name.replace("\\", "/")
        lower = normalized.lower()
        public_runtime_file = lower.endswith("/certifi/cacert.pem") or (
            "/bin/libreoffice/help/" in lower and lower.endswith(".key")
        )
        if FORBIDDEN_NAMES.search(normalized) and not public_runtime_file:
            self.errors.append(f"禁止的文件名：{logical_name}")
        if source and TEST_DOCUMENTS.search(normalized):
            self.errors.append(f"源码归档含测试文档：{logical_name}")
        if edition == "ocr" and any(
            value in lower
            for value in ("libreoffice", "pywin32", "win32com", "pythoncom")
        ):
            self.errors.append(f"OCR 版含 Office 组件：{logical_name}")
        if edition == "ocr" and Path(lower).suffix in {".doc", ".docx", ".wps"}:
            self.errors.append(f"OCR 版含 Office 文档：{logical_name}")

    def contents(self, logical_name: str, data: bytes) -> None:
        if len(data) > 2 * 1024 * 1024:
            return
        if LOCAL_PATH.search(data):
            self.errors.append(f"文件含本机绝对路径：{logical_name}")
        for pattern in SECRET_PATTERNS:
            if pattern.search(data):
                self.errors.append(f"文件疑似含密钥或令牌：{logical_name}")
                break
        if logical_name.endswith("build-info.json"):
            try:
                self.build_infos.append(json.loads(data.decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.errors.append(f"构建元数据无效：{logical_name}")

    def file(self, path: Path, logical_name: str, *, source: bool = False, edition: str = "") -> None:
        self.name(logical_name, source=source, edition=edition)
        if path.suffix.lower() in TEXT_SUFFIXES or path.name == "build-info.json":
            try:
                self.contents(logical_name, path.read_bytes())
            except OSError as exc:
                self.errors.append(f"无法读取 {logical_name}: {exc}")


def audit_source(root: Path, audit: Audit) -> None:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    )
    for raw_name in completed.stdout.split(b"\0"):
        if not raw_name:
            continue
        name = raw_name.decode("utf-8", errors="surrogateescape")
        path = root / name
        if path.is_file():
            audit.file(path, name, source=True)
    image = root / "docs" / "images" / "macos-main-window.png"
    if image.is_file():
        try:
            from PIL import Image

            with Image.open(image) as screenshot:
                if screenshot.getexif() or screenshot.info:
                    audit.errors.append(
                        "公开截图仍含元数据：docs/images/macos-main-window.png"
                    )
        except Exception as exc:
            audit.errors.append(f"无法检查公开截图：{exc}")


def audit_zip(path: Path, audit: Audit, edition: str) -> None:
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            audit.name(member.filename, edition=edition)
            if (
                not member.is_dir()
                and (PurePosixPath(member.filename).suffix.lower() in TEXT_SUFFIXES
                     or member.filename.endswith("build-info.json"))
                and member.file_size <= 2 * 1024 * 1024
            ):
                audit.contents(f"{path.name}:{member.filename}", archive.read(member))


def run_payload(path: Path) -> bytes:
    data = path.read_bytes()
    marker = b"\n__DOCUMENT_OCR_PAYLOAD__\n"
    offset = data.find(marker)
    if offset < 0:
        raise RuntimeError("找不到自解压 payload 标记")
    return data[offset + len(marker):]


def audit_run(path: Path, audit: Audit, edition: str) -> None:
    with tarfile.open(fileobj=io.BytesIO(run_payload(path)), mode="r:gz") as archive:
        for member in archive.getmembers():
            audit.name(member.name, edition=edition)
            suffix = PurePosixPath(member.name).suffix.lower()
            if member.isfile() and member.size <= 2 * 1024 * 1024 and (
                suffix in TEXT_SUFFIXES or member.name.endswith("build-info.json")
            ):
                stream = archive.extractfile(member)
                if stream:
                    audit.contents(f"{path.name}:{member.name}", stream.read())


def audit_dmg(path: Path, audit: Audit, edition: str) -> None:
    if os.uname().sysname != "Darwin":
        raise RuntimeError("DMG 递归审计必须在 macOS 执行")
    with tempfile.TemporaryDirectory(prefix="document-ocr-dmg-audit-") as temporary:
        mountpoint = Path(temporary) / "mount"
        mountpoint.mkdir()
        subprocess.run(
            ["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(mountpoint), str(path)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        try:
            for candidate in mountpoint.rglob("*"):
                if candidate.is_file() and not candidate.is_symlink():
                    audit.file(
                        candidate,
                        f"{path.name}:{candidate.relative_to(mountpoint).as_posix()}",
                        edition=edition,
                    )
        finally:
            subprocess.run(
                ["hdiutil", "detach", str(mountpoint)],
                check=False,
                stdout=subprocess.DEVNULL,
            )


def audit_assets(dist: Path, version: str, audit: Audit) -> None:
    expected = asset_names(version)
    present = sorted(
        path.name for path in dist.iterdir()
        if path.is_file() and path.suffix.lower() in {".dmg", ".zip", ".run"}
        and path.name.startswith(f"document-ocr-assistant-{version}-")
    )
    if sorted(expected) != present:
        audit.errors.append(
            "发布资产名称或数量不符；expected=" + repr(sorted(expected)) + "; actual=" + repr(present)
        )
        return
    for name in expected:
        path = dist / name
        edition = "ocr" if name.rsplit(".", 1)[0].endswith("-ocr") else "full"
        before = len(audit.build_infos)
        if path.suffix == ".zip":
            audit_zip(path, audit, edition)
        elif path.suffix == ".run":
            audit_run(path, audit, edition)
        else:
            audit_dmg(path, audit, edition)
        infos = audit.build_infos[before:]
        if not infos or not any(info.get("edition") == edition for info in infos):
            audit.errors.append(f"资产缺少正确 edition 的 build-info.json：{name}")
    checksums = dist / "SHA256SUMS.txt"
    if not checksums.is_file() or len(checksums.read_text(encoding="utf-8").splitlines()) != 8:
        audit.errors.append("SHA256SUMS.txt 缺失或不是 8 行")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit source and all frozen release assets")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dist", type=Path)
    parser.add_argument("--version", default="0.2.0")
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument("--assets-only", action="store_true")
    args = parser.parse_args()
    audit = Audit()
    if not args.assets_only:
        audit_source(args.root.resolve(), audit)
    if not args.source_only:
        audit_assets((args.dist or args.root / "dist").resolve(), args.version, audit)
    if audit.errors:
        print("发行审计失败：")
        print("\n".join(f"- {error}" for error in audit.errors))
        return 1
    print("发行审计通过：未发现敏感文件、测试文档或版本矩阵异常。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
