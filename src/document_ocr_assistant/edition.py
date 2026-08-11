from __future__ import annotations

import json
import os
import platform
import sys
from dataclasses import dataclass
from functools import lru_cache

from . import __version__
from .models import ProductEdition
from .runtime import runtime_roots


@dataclass(frozen=True, slots=True)
class BuildInfo:
    edition: ProductEdition = ProductEdition.FULL
    version: str = __version__
    platform_name: str = ""
    architecture: str = ""

    @property
    def display_suffix(self) -> str:
        return "OCR版" if self.edition is ProductEdition.OCR else "完整版"


@lru_cache(maxsize=1)
def build_info() -> BuildInfo:
    for root in runtime_roots():
        candidate = root / "build-info.json"
        if not candidate.is_file():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            return BuildInfo(
                edition=ProductEdition(str(payload["edition"])),
                version=str(payload.get("version") or __version__),
                platform_name=str(payload.get("platform") or ""),
                architecture=str(payload.get("architecture") or ""),
            )
        except (OSError, KeyError, TypeError, ValueError):
            continue
    # The override exists only for source-tree tests and cannot change a frozen build.
    if not getattr(sys, "frozen", False):
        try:
            return BuildInfo(edition=ProductEdition(os.environ.get("DOCUMENT_OCR_DEV_EDITION", "full")))
        except ValueError:
            pass
    return BuildInfo()


def is_full_edition() -> bool:
    return build_info().edition is ProductEdition.FULL


def version_banner() -> str:
    info = build_info()
    platform_name = info.platform_name or platform.system().lower()
    architecture = info.architecture or platform.machine().lower()
    return (
        f"文档OCR助手 {info.version} "
        f"({info.edition.value}, {platform_name}, {architecture})"
    )
