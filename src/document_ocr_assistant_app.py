"""PyInstaller-friendly top-level entry point."""

import sys


def dispatch() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        from document_ocr_assistant.cli import main

        return main(sys.argv[2:])

    from document_ocr_assistant.__main__ import main

    return main()


if __name__ == "__main__":
    raise SystemExit(dispatch())
