"""
RQ job for PDF extraction using PyMuPDF with S3 integration.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from rq import get_current_job
from rq.decorators import job

from extralit_ocr.extract import extract_markdown_with_hierarchy
from extralit_server.api.schemas.v1.document.metadata import DocumentProcessingMetadata
from extralit_server.contexts.files import download_file_content, get_minio_client
from extralit_server.database import SyncSessionLocal
from extralit_server.jobs.queues import OCR_QUEUE, REDIS_CONNECTION
from extralit_server.models.database import Document

_LOGGER = logging.getLogger(__name__)


@job(queue=OCR_QUEUE, connection=REDIS_CONNECTION, timeout=900, result_ttl=3600)
def pymupdf_to_markdown_job(
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
        client = get_minio_client()
        if client is None:
            raise Exception("Failed to get storage client")

        pdf_data = download_file_content(client, s3_url)
        _LOGGER.info(f"Downloaded PDF from S3: {s3_url} ({len(pdf_data)} bytes)")

        # Step 2: Extract markdown using PyMuPDF
        extraction_start = time.time()
        markdown, extraction_metadata = extract_markdown_with_hierarchy(pdf_data, filename)
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
        with SyncSessionLocal() as db:
            document = db.get(Document, document_id)
            if document and document.metadata_:
                metadata = DocumentProcessingMetadata(**document.metadata_)

                # Add text extraction metadata
                from extralit_server.api.schemas.v1.document.metadata import TextExtractionMetadata

                metadata.text_extraction_metadata = TextExtractionMetadata(
                    markdown=markdown,
                    extraction_method="pymupdf4llm",
                    text_extraction_completed_at=datetime.now(timezone.utc).isoformat(),
                )

                document.metadata_ = metadata.model_dump()
                db.commit()
                _LOGGER.info(f"Updated document {document_id} metadata with extraction results")

        current_job.meta.update(
            {"completed_at": datetime.now(timezone.utc).isoformat(), "success": True, "text_length": len(markdown)}
        )
        current_job.save_meta()

        return result

    except Exception as e:
        _LOGGER.error(f"Error in PyMuPDF extraction for document {document_id}: {e}")
        current_job.meta.update(
            {"completed_at": datetime.now(timezone.utc).isoformat(), "success": False, "error": str(e)}
        )
        current_job.save_meta()
        raise
