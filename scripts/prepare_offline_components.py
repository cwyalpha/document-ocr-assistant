#!/usr/bin/env python3
"""Prepare the bundled Kylin runtime from LocalKB offline components.

This installer deliberately does not use apt, dpkg, dnf, or rpm.  It reads the
LibreOffice ``.deb`` archives directly and creates a portable user-space tree,
which also makes it usable in an RPM-based Kylin installation.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
from pathlib import Path


PPOCRV6_MEDIUM_HASHES = {
    "PP-OCRv6_det_medium.onnx": "92078b7355007ccfffcd4c8cd441a3afd4538904d06881b29a155e1e679907c2",
    "PP-OCRv6_rec_medium.onnx": "eef444829dbbe18d7fea59a3f6eb75647518d2b3a9568d27c92e42940204894b",
    "ch_ppocr_mobile_v2.0_cls_mobile.onnx": "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c",
}
TABLE_MODEL_HASH = "d57a942af6a2f57d6a4a0372573c696a2379bf5857c45e2ac69993f3b334514b"
ORIENTATION_MODEL_HASH = "2f62c9bfb830a0b417241269fde7ef2d0ad5446c0ed2b8af33b1f6543545e8e2"
LIBREOFFICE_VERSION = "7.6.7.2"
LIBREOFFICE_HASHES = {
    f"LibreOffice_{LIBREOFFICE_VERSION}_Linux_x86-64_deb.tar.gz":
        "5fbd379bd9cedb037fa00b6e7e830619bff503a9451bc321e2b4e8d646081920",
    f"LibreOffice_{LIBREOFFICE_VERSION}_Linux_x86-64_deb_langpack_zh-CN.tar.gz":
        "80f8707ae9e7e72ed6a397724d876999233ec9d7a85f8c3fbb018621db95eb15",
}
LIBREOFFICE_NSS_REQUIRED = (
    "libnspr4.so",
    "libnss3.so",
    "libnssutil3.so",
    "libplc4.so",
    "libplds4.so",
    "libsmime3.so",
    "libssl3.so",
)
LIBREOFFICE_NSS_OPTIONAL = (
    "libfreebl3.so",
    "libfreeblpriv3.so",
    "libnssckbi.so",
    "libnssdbm3.so",
    "libnsssysinit.so",
    "libsoftokn3.so",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_verified(source: Path, target: Path, expected_hash: str) -> None:
    actual = _sha256(source)
    if actual != expected_hash:
        raise RuntimeError(
            f"SHA-256 mismatch for {source.name}: expected {expected_hash}, got {actual}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _ar_members(contents: bytes) -> dict[str, bytes]:
    """Read the simple ar format used by Debian packages."""
    if not contents.startswith(b"!<arch>\n"):
        raise RuntimeError("Invalid Debian/ar package header")
    result: dict[str, bytes] = {}
    offset = 8
    while offset + 60 <= len(contents):
        header = contents[offset : offset + 60]
        if header[58:60] != b"`\n":
            raise RuntimeError("Invalid Debian/ar member header")
        name = header[:16].decode("ascii", errors="replace").strip().rstrip("/")
        try:
            size = int(header[48:58].decode("ascii").strip())
        except ValueError as exc:
            raise RuntimeError("Invalid Debian/ar member size") from exc
        start = offset + 60
        result[name] = contents[start : start + size]
        offset = start + size + (size % 2)
    return result


def _safe_tar_extract(archive: tarfile.TarFile, target: Path) -> None:
    target_resolved = target.resolve()
    for member in archive.getmembers():
        candidate = (target / member.name).resolve()
        try:
            candidate.relative_to(target_resolved)
        except ValueError as exc:
            raise RuntimeError(f"Unsafe package path: {member.name}") from exc
    # These are trusted vendor packages. Symlinks inside the portable runtime
    # are required by LibreOffice and are preserved by tarfile.
    archive.extractall(target, filter="fully_trusted")


def _extract_deb_bytes(contents: bytes, target: Path, package_name: str) -> None:
    members = _ar_members(contents)
    data_name = next((name for name in members if name.startswith("data.tar")), None)
    if not data_name:
        raise RuntimeError(f"No data archive in {package_name}")
    try:
        with tarfile.open(fileobj=io.BytesIO(members[data_name]), mode="r:*") as payload:
            _safe_tar_extract(payload, target)
    except tarfile.ReadError as exc:
        raise RuntimeError(
            f"Unsupported compression in {package_name}/{data_name}; use the LocalKB 7.6.7.2 bundle"
        ) from exc


def _extract_deb_bundle(bundle: Path, target: Path) -> int:
    count = 0
    with tarfile.open(bundle, mode="r:*") as outer:
        for member in outer.getmembers():
            if not member.isfile() or not member.name.lower().endswith(".deb"):
                continue
            stream = outer.extractfile(member)
            if stream is None:
                continue
            _extract_deb_bytes(stream.read(), target, Path(member.name).name)
            count += 1
    if not count:
        raise RuntimeError(f"No .deb packages found in {bundle}")
    return count


def _find_libreoffice_bundles(components: Path) -> tuple[Path, Path | None]:
    main = components / f"LibreOffice_{LIBREOFFICE_VERSION}_Linux_x86-64_deb.tar.gz"
    language = components / (
        f"LibreOffice_{LIBREOFFICE_VERSION}_Linux_x86-64_deb_langpack_zh-CN.tar.gz"
    )
    if not main.is_file():
        raise FileNotFoundError(f"缺少固定版本 LibreOffice：{main}")
    for bundle in (main, language):
        if bundle.is_file():
            actual = _sha256(bundle)
            expected = LIBREOFFICE_HASHES[bundle.name]
            if actual != expected:
                raise RuntimeError(
                    f"SHA-256 mismatch for {bundle.name}: expected {expected}, got {actual}"
                )
    return main, language if language.is_file() else None


def install_libreoffice(components: Path, output_root: Path) -> Path:
    main, language = _find_libreoffice_bundles(components)
    destination = output_root / "bin" / "libreoffice"
    if destination.exists():
        shutil.rmtree(destination)
    print(f"[offline] extracting {main.name}")
    with tempfile.TemporaryDirectory(prefix="document_ocr_lo_") as temporary:
        staging = Path(temporary)
        _extract_deb_bundle(main, staging)
        if language:
            print(f"[offline] extracting {language.name}")
            _extract_deb_bundle(language, staging)
        candidates = sorted(
            path for path in (staging / "opt").glob("libreoffice*") if path.is_dir()
        )
        if not candidates:
            raise RuntimeError("LibreOffice runtime was not found after package extraction")
        shutil.copytree(candidates[-1], destination, symlinks=True)

    # LibreOffice's optional Python macro loader embeds the vendor's Python
    # 3.8 runtime. On Kylin V10 it can segfault while registering services,
    # before an ordinary Writer conversion starts. OCR only needs document
    # import/export, not Python macros, so exclude those optional services.
    services = destination / "program" / "services"
    for name in ("pyuno.rdb", "scriptproviderforpython.rdb"):
        component = services / name
        if component.is_file():
            component.rename(component.with_suffix(component.suffix + ".disabled"))

    for name in ("soffice", "soffice.bin"):
        executable = destination / "program" / name
        if executable.is_file():
            executable.chmod(
                executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            )
    library_sources = (Path("/usr/lib64"), Path("/lib64"))
    missing: list[str] = []
    copied: set[str] = set()
    for name in (*LIBREOFFICE_NSS_REQUIRED, *LIBREOFFICE_NSS_OPTIONAL):
        source = next(
            (directory / name for directory in library_sources if (directory / name).is_file()),
            None,
        )
        if source is None:
            if name in LIBREOFFICE_NSS_REQUIRED:
                missing.append(name)
            continue
        shutil.copy2(source.resolve(), destination / "program" / name)
        copied.add(name)
    if missing:
        raise RuntimeError(
            "Kylin NSS runtime is incomplete; missing: " + ", ".join(sorted(missing))
        )
    print(f"[offline] Kylin NSS runtime -> {len(copied)} libraries")
    soffice = destination / "program" / "soffice"
    if not soffice.is_file():
        raise RuntimeError("Bundled soffice executable is missing")
    print(f"[offline] LibreOffice -> {soffice}")
    return soffice


def install_models(
    components: Path,
    output_root: Path,
    table_model: Path | None,
    orientation_model: Path | None,
) -> None:
    source = components / "rapidocr-ppocrv6-medium"
    destination = output_root / "models" / "ppocrv6-medium"
    for name, expected in PPOCRV6_MEDIUM_HASHES.items():
        model = source / name
        if not model.is_file():
            raise FileNotFoundError(model)
        _copy_verified(model, destination / name, expected)
    print(f"[offline] PP-OCRv6 Medium -> {destination}")
    if table_model:
        _copy_verified(
            table_model,
            output_root / "models" / "table" / "slanet-plus.onnx",
            TABLE_MODEL_HASH,
        )
        print(f"[offline] SLANet-plus -> {output_root / 'models' / 'table'}")
    if orientation_model:
        _copy_verified(
            orientation_model,
            output_root / "models" / "orientation" / "rapid_orientation.onnx",
            ORIENTATION_MODEL_HASH,
        )
        print(f"[offline] page orientation -> {output_root / 'models' / 'orientation'}")


def install_archive_tools(components: Path, output_root: Path) -> list[Path]:
    bundles = sorted(components.glob("rarlinux-x64-*.tar.gz"))
    bundles += sorted(components.glob("7z*-linux-x64.tar.xz"))
    destination = output_root / "bin" / "unrar"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    installed: list[Path] = []
    wanted = {"unrar", "7zz", "7z"}
    for bundle in bundles:
        print(f"[offline] extracting {bundle.name}")
        with tempfile.TemporaryDirectory(prefix="document_ocr_archive_") as temporary:
            staging = Path(temporary)
            with tarfile.open(bundle, mode="r:*") as archive:
                _safe_tar_extract(archive, staging)
            for executable in staging.rglob("*"):
                if not executable.is_file() or executable.name not in wanted:
                    continue
                target = destination / executable.name
                shutil.copy2(executable, target)
                target.chmod(
                    target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                )
                if target not in installed:
                    installed.append(target)
    if not any(path.name == "unrar" for path in installed):
        raise RuntimeError("LocalKB offline unrar executable was not found")
    print(f"[offline] archive tools -> {destination}")
    return installed


def verify_libreoffice(soffice: Path, output_root: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="document_ocr_lo_verify_") as temporary:
        root = Path(temporary)
        home = root / "home"
        output = root / "output"
        profile = root / "profile"
        home.mkdir()
        output.mkdir()
        source = root / "smoke.html"
        source.write_text(
            "<html><body><p>Document OCR LibreOffice smoke test</p></body></html>",
            encoding="utf-8",
        )
        environment = os.environ.copy()
        environment.setdefault("SAL_USE_VCLPLUGIN", "svp")
        environment["HOME"] = str(home)
        environment["XDG_CONFIG_HOME"] = str(home / ".config")
        # Mirror the frozen application's runtime library path when checking
        # the bundled child process before the final package is assembled.
        internal_library_dirs = []
        root_internal = output_root / "_internal"
        if root_internal.is_dir():
            internal_library_dirs.append(root_internal)
        internal_library_dirs.extend(sorted((output_root / "app").glob("*/_internal")))
        if internal_library_dirs:
            library_path = os.pathsep.join(str(path) for path in internal_library_dirs)
            existing_library_path = environment.get("LD_LIBRARY_PATH")
            if existing_library_path:
                library_path = os.pathsep.join((library_path, existing_library_path))
            environment["LD_LIBRARY_PATH"] = library_path
        completed = subprocess.run(
            [
                str(soffice),
                "--headless",
                "--nologo",
                "--nodefault",
                "--norestore",
                f"-env:UserInstallation={profile.resolve().as_uri()}",
                "--convert-to",
                "txt:Text",
                "--outdir",
                str(output),
                str(source),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
            check=False,
            env=environment,
        )
        converted = output / "smoke.txt"
        if completed.returncode or not converted.is_file():
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f"Bundled LibreOffice conversion self-check failed: {detail}")
        print("[offline] LibreOffice headless conversion self-check passed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare Kylin offline OCR components")
    parser.add_argument("--components-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--table-model", type=Path)
    parser.add_argument("--orientation-model", type=Path)
    parser.add_argument("--skip-libreoffice", action="store_true")
    parser.add_argument("--skip-models", action="store_true")
    parser.add_argument("--skip-archive-tools", action="store_true")
    parser.add_argument("--no-verify", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    components = args.components_dir.resolve()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    if not components.is_dir():
        raise FileNotFoundError(components)
    soffice = None
    if not args.skip_libreoffice:
        soffice = install_libreoffice(components, output_root)
    if not args.skip_models:
        install_models(
            components, output_root, args.table_model, args.orientation_model
        )
    if not args.skip_archive_tools:
        install_archive_tools(components, output_root)
    if soffice and not args.no_verify:
        verify_libreoffice(soffice, output_root)
    print("[offline] components are ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
