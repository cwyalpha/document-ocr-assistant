#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path


PPOCRV6_MEDIUM_HASHES = {
    "PP-OCRv6_det_medium.onnx": "92078b7355007ccfffcd4c8cd441a3afd4538904d06881b29a155e1e679907c2",
    "PP-OCRv6_rec_medium.onnx": "eef444829dbbe18d7fea59a3f6eb75647518d2b3a9568d27c92e42940204894b",
    "ch_ppocr_mobile_v2.0_cls_mobile.onnx": "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c",
}
TABLE_MODEL_HASH = "d57a942af6a2f57d6a4a0372573c696a2379bf5857c45e2ac69993f3b334514b"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_verified(source: Path, target: Path, expected: str) -> None:
    actual = sha256(source)
    if actual != expected:
        raise RuntimeError(f"SHA-256 mismatch for {source}: expected {expected}, got {actual}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def find_unrar(root: Path) -> Path:
    candidates = [
        root / "src" / "unrar.exe",
        root / "unrar.exe",
        root / "build_dist" / "dist" / "unrar.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    matches = list(root.rglob("unrar.exe"))
    if matches:
        return matches[0]
    raise FileNotFoundError(f"Windows unrar.exe was not found under {root}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Windows OCR portable runtime")
    parser.add_argument("--components-dir", type=Path, required=True)
    parser.add_argument("--localkb-windows-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--table-model", type=Path, required=True)
    parser.add_argument("--unrar", type=Path)
    args = parser.parse_args()

    output = args.output_root.resolve()
    model_source = args.components_dir.resolve() / "rapidocr-ppocrv6-medium"
    model_target = output / "models" / "ppocrv6-medium"
    for name, expected in PPOCRV6_MEDIUM_HASHES.items():
        copy_verified(model_source / name, model_target / name, expected)
    copy_verified(
        args.table_model.resolve(),
        output / "models" / "table" / "slanet-plus.onnx",
        TABLE_MODEL_HASH,
    )
    unrar = args.unrar.resolve() if args.unrar else find_unrar(args.localkb_windows_root.resolve())
    archive_target = output / "bin" / "archive" / "unrar.exe"
    archive_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(unrar, archive_target)
    print(f"[windows] PP-OCRv6 Medium -> {model_target}")
    print(f"[windows] SLANet-plus -> {output / 'models' / 'table'}")
    print(f"[windows] unrar -> {archive_target}")
    print("[windows] LibreOffice intentionally excluded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

