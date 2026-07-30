"""PyInstaller-friendly command-line entry point."""

from document_ocr_assistant.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
