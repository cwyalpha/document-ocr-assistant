from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from document_ocr_assistant.archives import ArchiveError, ArchiveSession, extract_archive
from document_ocr_assistant.models import (
    InputItem,
    InputKind,
    OutputMode,
    ProcessResult,
    ProcessingOptions,
)
from document_ocr_assistant.pipeline import ProcessingPipeline


class LegacyNameZipInfo(zipfile.ZipInfo):
    """Write raw legacy filename bytes without ZIP's UTF-8 flag."""

    def __init__(self, raw_name: bytes) -> None:
        self.raw_name = raw_name
        super().__init__(raw_name.decode("cp437"))

    def _encodeFilenameFlags(self):  # noqa: N802 - zipfile private API spelling
        return self.raw_name, self.flag_bits & ~0x800


def test_zip_archive_expands_supported_files(tmp_path: Path) -> None:
    archive = tmp_path / "资料.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("nested/scan.png", b"not-a-real-image")
        stream.writestr("nested/readme.txt", b"ignored")

    with ArchiveSession(archive) as items:
        assert len(items) == 1
        assert items[0].kind is InputKind.IMAGE
        assert items[0].virtual_path == Path("nested/scan.png")
        assert items[0].source_path.exists()
    assert not items[0].source_path.exists()


def test_archive_unconverted_files_are_copied_with_original_hierarchy(tmp_path: Path) -> None:
    archive = tmp_path / "项目资料.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("images/scan.png", b"image-placeholder")
        stream.writestr("notes/readme.txt", "保留说明".encode("utf-8"))
        stream.writestr("data/config.json", b'{"enabled": true}')
        stream.writestr("tables/source.xlsx", b"xlsx-placeholder")

    class FakeProcessors:
        def process(self, item, options, progress=None, cancelled=None):
            if progress:
                progress(100, "测试识别完成")
            return ProcessResult("测试文字", "测试文字\n")

    output = tmp_path / "批次"
    options = ProcessingOptions(
        output_mode=OutputMode.NEW_BATCH_DIRECTORY,
        batch_directory=output,
        copy_unconverted_files=True,
    )
    results = ProcessingPipeline(FakeProcessors()).process_item(
        InputItem(archive, InputKind.ARCHIVE), options
    )

    archive_output = output / "项目资料_ocr"
    assert (archive_output / "images" / "scan_ocr.txt").read_text(encoding="utf-8") == "测试文字\n"
    assert (archive_output / "images" / "scan_ocr.md").read_text(encoding="utf-8") == "测试文字\n"
    assert (archive_output / "notes" / "readme.txt").read_text(encoding="utf-8") == "保留说明"
    assert (archive_output / "data" / "config.json").read_bytes() == b'{"enabled": true}'
    assert (archive_output / "tables" / "source.xlsx").read_bytes() == b"xlsx-placeholder"
    assert len(results) == 1
    assert len(results[0].outputs) == 5


def test_zip_path_traversal_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("../../outside.png", b"bad")
    with pytest.raises(ArchiveError, match="不安全路径"):
        extract_archive(archive, tmp_path / "target")


def test_zip_gbk_filename_is_decoded_consistently(tmp_path: Path) -> None:
    archive = tmp_path / "发票.zip"
    expected = "陈唯源发票26357000000103160134.pdf"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr(LegacyNameZipInfo(expected.encode("gbk")), b"pdf-placeholder")

    with ArchiveSession(archive) as items:
        assert [item.virtual_path for item in items] == [Path(expected)]
        assert items[0].source_path.name == expected


def test_zip_utf8_filename_without_flag_is_recovered(tmp_path: Path) -> None:
    archive = tmp_path / "utf8-no-flag.zip"
    expected = "目录/电子发票.pdf"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr(LegacyNameZipInfo(expected.encode("utf-8")), b"pdf-placeholder")

    with ArchiveSession(archive) as items:
        assert [item.virtual_path for item in items] == [Path(expected)]


def test_tar_symlinks_are_not_extracted(tmp_path: Path) -> None:
    archive = tmp_path / "links.tar"
    with tarfile.open(archive, "w") as stream:
        payload = b"ok"
        ordinary = tarfile.TarInfo("folder/image.png")
        ordinary.size = len(payload)
        stream.addfile(ordinary, io.BytesIO(payload))
        link = tarfile.TarInfo("folder/link.png")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        stream.addfile(link)
    target = tmp_path / "target"
    extract_archive(archive, target)
    assert (target / "folder/image.png").read_bytes() == b"ok"
    assert not (target / "folder/link.png").exists()


def test_tar_gz_archive_is_supported(tmp_path: Path) -> None:
    archive = tmp_path / "扫描资料.tar.gz"
    payload = b"image-placeholder"
    with tarfile.open(archive, "w:gz") as stream:
        member = tarfile.TarInfo("nested/scan.jpg")
        member.size = len(payload)
        stream.addfile(member, io.BytesIO(payload))

    with ArchiveSession(archive) as items:
        assert len(items) == 1
        assert items[0].kind is InputKind.IMAGE
        assert items[0].virtual_path == Path("nested/scan.jpg")


def test_encrypted_7z_requests_password(tmp_path: Path) -> None:
    py7zr = pytest.importorskip("py7zr")
    source = tmp_path / "scan.png"
    source.write_bytes(b"image-placeholder")
    archive = tmp_path / "encrypted.7z"
    with py7zr.SevenZipFile(archive, "w", password="secret") as stream:
        stream.write(source, "nested/scan.png")

    requested: list[Path] = []

    def password_provider(path: Path) -> str:
        requested.append(path)
        return "secret"

    with ArchiveSession(archive, password_provider) as items:
        assert [item.virtual_path for item in items] == [Path("nested/scan.png")]
    assert requested == [archive]
