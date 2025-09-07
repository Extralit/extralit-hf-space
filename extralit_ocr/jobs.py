"""
RQ job for PDF extraction using PyMuPDF with S3 integration.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from extralit_server.api.schemas.v1.document.metadata import DocumentProcessingMetadata, TextExtractionMetadata
from extralit_server.contexts.files import download_file_content, get_s3_client
from extralit_server.database import AsyncSessionLocal
from extralit_server.jobs.queues import OCR_QUEUE, REDIS_CONNECTION
from extralit_server.models.database import Document
from rq import get_current_job
from rq.decorators import job

from extralit_ocr.extract import ExtractionConfig, extract_markdown_with_hierarchy

_LOGGER = logging.getLogger(__name__)


def _get_document_margins(metadata: DocumentProcessingMetadata) -> tuple[int, int, int, int] | None:
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
            print(f"No layout analysis or margin data found in \n{metadata}")
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
            print(f"Using document-specific margins: {margins}")
            return margins

    except Exception as e:
        _LOGGER.warning(f"Error retrieving margins for document: {e}", exc_info=True)

    return None


@job(queue=OCR_QUEUE, connection=REDIS_CONNECTION, timeout=900, result_ttl=3600)
async def pymupdf_to_markdown_job(
    document_id: UUID, s3_url: str, filename: str, analysis_metadata: dict[str, Any], workspace_name: str
) -> dict[str, Any]:
    """
    Extract PDF text using PyMuPDF, downloading from S3.

    Args:
        document_id: UUID of document to process
        s3_url: S3 URL of the PDF file
        filename: Original filename
        analysis_metadata: Results from analysis_and_preprocess_job
        workspace_name: Workspace name for S3 operations

    Returns:
        Dictionary with extraction results
    """
    current_job = get_current_job()
    if current_job is None:
        raise Exception("No current job found")

    current_job.meta.update(
        {
            "document_id": str(document_id),
            "filename": filename,
            "workspace_name": workspace_name,
            "workflow_step": "pymupdf_extraction",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    current_job.save_meta()

    try:
        # Step 1: Download PDF from S3
        client = await get_s3_client()
        if client is None:
            raise Exception("Failed to get storage client")

        pdf_data = await download_file_content(client, s3_url)

        async with AsyncSessionLocal() as db:
            document: Document | None = await db.get(Document, document_id)
            if document is None:
                raise Exception(f"Document with ID {document_id} not found in database")

            if document and document.metadata_:
                metadata = DocumentProcessingMetadata(**document.metadata_)
            else:
                metadata = DocumentProcessingMetadata()

            margins = _get_document_margins(metadata)
            if margins:
                config = ExtractionConfig(margins=margins)
            else:
                # Use default margins if none found
                config = ExtractionConfig()

            # Step 2: Extract markdown using PyMuPDF
            extraction_start = time.time()
            markdown, extraction_metadata = extract_markdown_with_hierarchy(pdf_data, filename, config=config)
            extraction_time = time.time() - extraction_start

            # Step 3: Prepare results
            result = {
                "document_id": str(document_id),
                "markdown": markdown,
                "extraction_metadata": extraction_metadata,
                "processing_time": extraction_time,
                "success": True,
            }

            # Step 4: Update document metadata in database
            metadata.text_extraction_metadata = TextExtractionMetadata(
                markdown=markdown,
                extraction_method="pymupdf4llm",
            )

            document.metadata_ = metadata.model_dump()
            await db.commit()
            _LOGGER.info(f"Updated document {document_id} metadata with extraction results")

        current_job.meta.update({"success": True, "text_length": len(markdown)})
        current_job.save_meta()

        return result

    except Exception as e:
        _LOGGER.error(f"Error in PyMuPDF extraction for document {document_id}: {e}")
        current_job.meta.update({"success": False, "error": str(e)})
        current_job.save_meta()
        raise
