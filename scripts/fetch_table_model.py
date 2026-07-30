#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
import urllib.request
from pathlib import Path


URL = "https://www.modelscope.cn/models/RapidAI/RapidTable/resolve/v2.0.0/slanet-plus.onnx"
SHA256 = "d57a942af6a2f57d6a4a0372573c696a2379bf5857c45e2ac69993f3b334514b"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch the pinned SLANet-plus ONNX build asset")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_file() and digest(output) == SHA256:
        print(f"[model] cached and verified: {output}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        print(f"[model] downloading {URL}")
        with urllib.request.urlopen(URL, timeout=90) as response, temporary.open("wb") as target:
            shutil.copyfileobj(response, target)
        actual = digest(temporary)
        if actual != SHA256:
            raise RuntimeError(f"SLANet-plus SHA-256 mismatch: expected {SHA256}, got {actual}")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"[model] downloaded and verified: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

