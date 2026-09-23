"""Text extraction from uploaded knowledge-base files."""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf"}


def extract_text(filename: str, content: bytes) -> str:
    """Extract plain text from an uploaded file.

    Supports .txt / .md (utf-8 with fallback) and .pdf (via pypdf).
    Raises ValueError for unsupported types.
    """
    name = (filename or "").lower()
    if name.endswith((".txt", ".md", ".markdown")):
        for encoding in ("utf-8", "utf-16", "latin-1"):
            try:
                return content.decode(encoding)
            except (UnicodeDecodeError, ValueError):
                continue
        return content.decode("utf-8", errors="replace")
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError(
                "PDF support needs the 'pypdf' package (pip install pypdf)."
            ) from exc
        import io

        reader = PdfReader(io.BytesIO(content))
        pages: list[str] = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception as exc:
                log.warning("PDF page extraction failed: %s", exc)
        return "\n\n".join(p for p in pages if p.strip())
    raise ValueError(
        f"Unsupported file type for '{filename}'. "
        f"Supported: {sorted(SUPPORTED_EXTENSIONS)}"
    )
