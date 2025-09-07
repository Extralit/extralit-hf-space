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

import logging
from typing import Any, Optional
from uuid import UUID

from rq import get_current_job
from rq.decorators import job

from extralit_ocr.extract import ExtractionConfig, extract_markdown_with_hierarchy
from extralit_server.api.schemas.v1.document.metadata import DocumentProcessingMetadata
from extralit_server.jobs.queues import OCR_QUEUE, REDIS_CONNECTION

_LOGGER = logging.getLogger(__name__)

from extralit_server.contexts import files
from extralit_server.database import AsyncSessionLocal
from extralit_server.models.database import Document


async def _get_document_margins(document_id: UUID) -> Optional[tuple[int, int, int, int]]:
    """
    Fetch margins from document metadata in database.

    Returns:
        Tuple of (left, top, right, bottom) margins in PDF points, or None if not found
    """
    try:
        async with AsyncSessionLocal() as db:
            document = await db.get(Document, document_id)

            if not document or not document.metadata_:
                print(f"No metadata found for document {document_id}")
                return None

            metadata = DocumentProcessingMetadata(**document.metadata_)

            if (
                not metadata.analysis_metadata
                or not metadata.analysis_metadata.layout_analysis
                or not metadata.analysis_metadata.layout_analysis.margin_analysis
            ):
                print(f"No layout analysis or margin data found for document {document_id}")
                return None

            margin_analysis = metadata.analysis_metadata.layout_analysis.margin_analysis
            print("margin_analysis:", margin_analysis)

            # Convert pixels to PDF points (multiply by 0.75)
            if all(key in margin_analysis for key in ["left_px", "top_px", "right_px", "bottom_px"]):
                left = int(margin_analysis["left_px"] * 0.75)
                top = int(margin_analysis["top_px"] * 0.75)
                right = int(margin_analysis["right_px"] * 0.75)
                bottom = int(margin_analysis["bottom_px"] * 0.75)

                margins = (left, top, right, bottom)
                print(f"Using document-specific margins for {document.reference}: {margins}")
                return margins

    except Exception as e:
        _LOGGER.warning(f"Error retrieving margins for document {document_id}: {e}", exc_info=True)

    return None


@job(queue=OCR_QUEUE, connection=REDIS_CONNECTION, timeout=900, result_ttl=3600)
async def pymupdf_to_markdown_job(
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
        job.meta.update(
            {
                "document_id": str(document_id),
                "filename": filename,
                "workspace_name": workspace_name,
                "workflow_step": "pymupdf_extraction",
            }
        )
        job.save_meta()

    try:
        # Step 1: Download PDF from S3
        s3_client = await files.get_s3_client()
        pdf_data = await files.download_file_content(s3_client, s3_url)

        # Step 2: Get document-specific margins
        margins = await _get_document_margins(document_id)

        # Step 3: Create extraction config with margins
        if margins:
            config = ExtractionConfig(margins=margins)
        else:
            # Use default margins if none found
            config = ExtractionConfig()

        # Step 4: Extract markdown using PyMuPDF
        markdown_text, extraction_metadata = extract_markdown_with_hierarchy(pdf_data, filename, config=config)

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
            job.meta.update(
                {
                    "status": "completed",
                    "markdown_length": len(markdown_text),
                    "pages_processed": extraction_metadata.get("pages", 0),
                }
            )
            job.save_meta()

        _LOGGER.info(f"Successfully extracted {len(markdown_text)} characters from document {document_id}")
        return result

    except Exception as e:
        error_msg = f"Failed to extract markdown from document {document_id}: {e}"
        _LOGGER.error(error_msg)

        if job:
            job.meta.update(
                {
                    "status": "failed",
                    "error": str(e),
                }
            )
            job.save_meta()

        raise RuntimeError(error_msg) from e
