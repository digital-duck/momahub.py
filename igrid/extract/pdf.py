"""PDF text extraction with pluggable engines."""
from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import httpx


class PDFExtractor:
    """Extract text from PDFs.

    engine: 'pypdf' (fast, text-only) or 'docling' (layout-aware).
    max_chars: truncate output to this many characters.
    """

    def __init__(self, engine: str = "pypdf", max_chars: int = 12_000):
        if engine not in ("pypdf", "docling"):
            raise ValueError(f"Unknown engine: {engine!r}  (use 'pypdf' or 'docling')")
        self.engine = engine
        self.max_chars = max_chars

    def from_bytes(self, data: bytes) -> str:
        if self.engine == "docling":
            return self._docling(data)
        return self._pypdf(data)

    def from_file(self, path: str | Path) -> str:
        return self.from_bytes(Path(path).read_bytes())

    def from_url(self, url: str, timeout: float = 30.0) -> str:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        return self.from_bytes(resp.content)

    # -- engines ----------------------------------------------------------

    def _pypdf(self, data: bytes) -> str:
        import pypdf  # type: ignore

        reader = pypdf.PdfReader(io.BytesIO(data))
        parts: list[str] = []
        total = 0
        for page in reader.pages:
            text = page.extract_text() or ""
            parts.append(text)
            total += len(text)
            if total >= self.max_chars:
                break
        return "\n".join(parts)[: self.max_chars]

    def _docling(self, data: bytes) -> str:
        try:
            from docling.document_converter import DocumentConverter  # type: ignore
        except ImportError:
            # Graceful fallback to pypdf
            return self._pypdf(data)

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
                fh.write(data)
                tmp_path = fh.name
            converter = DocumentConverter()
            result = converter.convert(tmp_path)
            md = result.document.export_to_markdown()
            return md[: self.max_chars]
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
