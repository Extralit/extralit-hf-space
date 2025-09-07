from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pymupdf
import pymupdf4llm
from extralit_server.api.schemas.v1.document.metadata import (
    DocumentProcessingMetadata,
)

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class ExtractionConfig:
    write_dir: Optional[Path | str] = None
    write_mode: str = "overwrite"  # or "skip"
    margins: tuple[int, int, int, int] = (0, 50, 0, 30)
    header_detection_max_levels: int = 4
    header_detection_body_limit: int = 10
    safe_filename_timestamp: bool = True
    safe_filename_hash_len: int = 8

    # internal cached Path (not user supplied directly)
    _write_dir_path: Optional[Path] = field(init=False, default=None, repr=False)

    def __post_init__(self):
        if self.write_mode not in {"overwrite", "skip"}:
            raise ValueError("write_mode must be 'overwrite' or 'skip'")
        if self.write_dir:
            self._write_dir_path = Path(self.write_dir).expanduser().resolve()
            self._write_dir_path.mkdir(parents=True, exist_ok=True)

    @property
    def write_dir_path(self) -> Optional[Path]:
        return self._write_dir_path


def create_default_config() -> ExtractionConfig:
    return ExtractionConfig(
        write_dir=os.getenv("PDF_MARKDOWN_WRITE_DIR") or None,
        write_mode=os.getenv("PDF_MARKDOWN_WRITE_MODE", "overwrite"),
    )


# Singleton default config (can be overridden per call)
_DEFAULT_CONFIG = create_default_config()


def generate_safe_filename(
    original_name: str,
    include_timestamp: bool = True,
    hash_len: int = 8,
    suffix: str = ".md",
) -> str:
    """
    Produce a safe filename for storage - includes truncated stem, optional hash + timestamp.
    """
    stem = Path(original_name).stem[:80] or "document"
    parts = [stem]

    if hash_len > 0:
        digest = hashlib.sha1(original_name.encode("utf-8", errors="ignore")).hexdigest()[:hash_len]
        parts.append(digest)

    if include_timestamp:
        parts.append(str(int(time.time())))

    return "-".join(parts) + suffix


def write_markdown_output(
    markdown_text: str,
    original_filename: str,
    config: ExtractionConfig,
) -> Optional[str]:
    """
    Write markdown to disk if configured. Returns the absolute string path or None.
    """
    write_dir = config.write_dir_path
    if not write_dir:
        return None

    out_path = write_dir / generate_safe_filename(
        original_filename,
        include_timestamp=config.safe_filename_timestamp,
        hash_len=config.safe_filename_hash_len,
    )

    if out_path.exists() and config.write_mode == "skip":
        LOGGER.debug("Skipping existing markdown file (skip mode): %s", out_path)
        return str(out_path)

    out_path.write_text(markdown_text, encoding="utf-8")
    LOGGER.debug(
        "Wrote markdown output: %s (%d chars)",
        out_path,
        len(markdown_text),
    )
    return str(out_path)


def extract_document_margins(metadata: DocumentProcessingMetadata) -> tuple[int, int, int, int] | None:
    """
    Fetch margins from document metadata in database.

    Returns:
        Tuple of (left, top, right, bottom) margins in PDF points, or None if not found
    """
    try:
        if (
            not metadata.analysis_metadata
            or not metadata.analysis_metadata.layout_analysis
            or not metadata.analysis_metadata.layout_analysis.margin_analysis
        ):
            LOGGER.debug("No layout analysis or margin data found in document metadata")
            return None

        margin_analysis = metadata.analysis_metadata.layout_analysis.margin_analysis
        LOGGER.debug("Found margin analysis data: %s", margin_analysis)

        # Convert pixels to PDF points (multiply by 0.75)
        if all(key in margin_analysis for key in ["left_px", "top_px", "right_px", "bottom_px"]):
            left = int(margin_analysis["left_px"])
            top = int(margin_analysis["top_px"])
            right = int(margin_analysis["right_px"])
            bottom = int(margin_analysis["bottom_px"])

            margins = (left, top, right, bottom)
            LOGGER.info("Using document-specific margins: %s", margins)
            return margins

    except Exception as e:
        LOGGER.warning(f"Error retrieving margins for document: {e}", exc_info=True)

    return None


def extract_markdown_with_hierarchy(
    file_bytes: bytes,
    original_filename: str,
    *,
    config: Optional[ExtractionConfig] = None,
) -> tuple[str, dict[str, Any]]:
    """
    Extract hierarchical Markdown from a PDF (bytes) using either the embedded
    Table of Contents (TOC) or a heuristic header identification fallback.

    Args:
        file_bytes: Raw PDF bytes.
        original_filename: Original name (used only for generated markdown filename).
        config: Optional ExtractionConfig. If omitted, environment-derived default is used.

    Returns:
        A tuple: (markdown_text, metadata_dict)

    Raises:
        ValueError: On invalid input or extraction failure.
    """
    if not file_bytes:
        raise ValueError("Empty PDF content")

    cfg = config or _DEFAULT_CONFIG

    try:
        doc = pymupdf.open(stream=file_bytes)
    except Exception as e:  # pragma: no cover - external library specifics
        raise ValueError(f"Failed to open PDF: {e}") from e

    toc = doc.get_toc()
    toc_entry_count = len(toc) if toc else 0

    headers_strategy = ""
    header_levels_detected: Optional[int] = None

    try:
        if toc_entry_count > 0:
            headers_strategy = "toc"
            toc_headers = pymupdf4llm.TocHeaders(doc)
            md_text = pymupdf4llm.to_markdown(doc, hdr_info=toc_headers, margins=cfg.margins)
            # TOC format: list of [level, title, page_num]
            header_levels_detected = len({level for level, _, _ in toc})
            LOGGER.debug("Used TocHeaders with %d TOC entries", toc_entry_count)
        else:
            headers_strategy = "identify"
            identified = pymupdf4llm.IdentifyHeaders(
                doc,
                max_levels=cfg.header_detection_max_levels,
                body_limit=cfg.header_detection_body_limit,
            )
            md_text = pymupdf4llm.to_markdown(doc, hdr_info=identified, margins=cfg.margins)
            # Attempt to extract distinct levels if the object exposes .headers
            try:  # pragma: no cover - depends on library internals
                header_levels_detected = len({h.level for h in identified.headers})  # type: ignore[attr-defined]
            except Exception:
                header_levels_detected = None
            LOGGER.debug("Used IdentifyHeaders heuristic")
    except Exception as e:  # pragma: no cover - external library specifics
        raise ValueError(f"Markdown conversion failed: {e}") from e

    write_path = write_markdown_output(md_text, original_filename, cfg)

    metadata: dict[str, Any] = {
        "pages": doc.page_count,
        "toc_entries": toc_entry_count,
        "headers_strategy": headers_strategy,
        "header_levels_detected": header_levels_detected,
        "margins": {
            "left": cfg.margins[0],
            "top": cfg.margins[1],
            "right": cfg.margins[2],
            "bottom": cfg.margins[3],
        },
        "output_path": write_path,
        "output_size_chars": len(md_text),
    }
    return md_text, metadata


# ---------------------------------------------------------------------------
# Convenience / Public API
# ---------------------------------------------------------------------------


def should_extract_text(filename: str, file_metadata: dict[str, Any]) -> bool:
    """Determine if text extraction should be performed for a file."""
    if not filename.lower().endswith(".pdf"):
        return False

    return not file_metadata.get("text_extracted", False)
