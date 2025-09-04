# Copyright 2024-present, Extralit Labs, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""RQ jobs for PyMuPDF processing with document-specific margin support."""

import asyncio
import logging
from typing import Any, Optional, Tuple
from uuid import UUID

from rq import get_current_job

from ..extract import extract_markdown_with_hierarchy, ExtractionConfig

_LOGGER = logging.getLogger(__name__)

# Try to import database components for margin fetching
try:
    from extralit_server.contexts import files
    from extralit_server.database import SyncSessionLocal
    from extralit_server.models.database import Document
    HAS_EXTRALIT_SERVER = True
except ImportError:
    HAS_EXTRALIT_SERVER = False
    _LOGGER.warning("Extralit server components not available, using default margins")


def _get_document_margins(document_id: UUID) -> Optional[Tuple[int, int, int, int]]:
    """
    Fetch margins from document metadata in database.

    Returns:
        Tuple of (left, top, right, bottom) margins in PDF points, or None if not found
    """
    if not HAS_EXTRALIT_SERVER:
        return None

    try:
        with SyncSessionLocal() as session:
            document = session.query(Document).filter(Document.id == document_id).first()

            if not document or not document.metadata_:
                _LOGGER.info(f"No metadata found for document {document_id}")
                return None

            metadata = document.metadata_
            if isinstance(metadata, dict):
                analysis_metadata = metadata.get("analysis_metadata", {})
            else:
                analysis_metadata = getattr(metadata, "analysis_metadata", {}) or {}

            if isinstance(analysis_metadata, dict):
                layout_analysis = analysis_metadata.get("layout_analysis", {})
            else:
                layout_analysis = getattr(analysis_metadata, "layout_analysis", {}) or {}

            # Check for estimated_margins directly in layout_analysis (correct structure)
            if isinstance(layout_analysis, dict) and "estimated_margins" in layout_analysis:
                estimated_margins = layout_analysis["estimated_margins"]

                # Convert pixels to PDF points (multiply by 0.75)
                if all(key in estimated_margins for key in ["left_px", "top_px", "right_px", "bottom_px"]):
                    left = int(estimated_margins["left_px"] * 0.75)
                    top = int(estimated_margins["top_px"] * 0.75)
                    right = int(estimated_margins["right_px"] * 0.75)
                    bottom = int(estimated_margins["bottom_px"] * 0.75)

                    margins = (left, top, right, bottom)
                    _LOGGER.info(f"Using document-specific margins for {document_id}: {margins}")
                    return margins
                else:
                    _LOGGER.info(f"Incomplete margin data for document {document_id}")

    except Exception as e:
        _LOGGER.warning(f"Error retrieving margins for document {document_id}: {e}")

    return None


async def _download_file_from_s3(s3_url: str) -> bytes:
    """Download file content from S3 using existing extralit-server patterns."""
    if not HAS_EXTRALIT_SERVER:
        raise RuntimeError("S3 operations require extralit_server components")

    try:
        s3_client = await files.get_s3_client()
        return await files.download_file_content(s3_client, s3_url)
    except Exception as e:
        raise RuntimeError(f"Failed to download file from S3: {e}")


def pymupdf_to_markdown_job(
    document_id: UUID,
    s3_url: str,
    filename: str,
    job_metadata: dict[str, Any],
    workspace_name: str,
) -> dict[str, Any]:
    """
    RQ job to extract markdown from PDF using PyMuPDF with document-specific margins.

    Args:
        document_id: UUID of the document in the database
        s3_url: S3 URL of the PDF file to process
        filename: Original filename of the PDF
        job_metadata: Additional metadata for the job
        workspace_name: Name of the workspace

    Returns:
        Dictionary containing extraction results and metadata
    """
    job = get_current_job()
    if job:
        job.meta.update({
            "document_id": str(document_id),
            "filename": filename,
            "workspace_name": workspace_name,
            "workflow_step": "pymupdf_extraction",
        })
        job.save_meta()

    _LOGGER.info(f"Starting PyMuPDF extraction for document {document_id}")

    try:
        # Step 1: Download PDF from S3
        pdf_data = asyncio.run(_download_file_from_s3(s3_url))

        # Step 2: Get document-specific margins
        margins = _get_document_margins(document_id)

        # Step 3: Create extraction config with margins
        if margins:
            config = ExtractionConfig(margins=margins)
            _LOGGER.info(f"Using document-specific margins: {margins}")
        else:
            # Use default margins if none found
            config = ExtractionConfig()
            _LOGGER.info("Using default margins")

        # Step 4: Extract markdown using PyMuPDF
        markdown_text, extraction_metadata = extract_markdown_with_hierarchy(
            pdf_data, filename, config=config
        )

        # Step 5: Prepare result
        result = {
            "document_id": str(document_id),
            "markdown": markdown_text,
            "extraction_metadata": extraction_metadata,
            "margins_used": {
                "left": config.margins[0],
                "top": config.margins[1],
                "right": config.margins[2],
                "bottom": config.margins[3],
            },
            "filename": filename,
            "status": "completed",
        }

        if job:
            job.meta.update({
                "status": "completed",
                "markdown_length": len(markdown_text),
                "pages_processed": extraction_metadata.get("pages", 0),
            })
            job.save_meta()

        _LOGGER.info(f"Successfully extracted {len(markdown_text)} characters from document {document_id}")
        return result

    except Exception as e:
        error_msg = f"Failed to extract markdown from document {document_id}: {e}"
        _LOGGER.error(error_msg)

        if job:
            job.meta.update({
                "status": "failed",
                "error": str(e),
            })
            job.save_meta()

        raise RuntimeError(error_msg) from e
