"""
Pydantic schemas for the PDF extraction service.

This module defines the data models used for API requests and responses,
ensuring type safety and validation across HTTP endpoints and RQ jobs.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class PDFMetadata(BaseModel):
    """
    Metadata about PDF processing and extraction results.

    This schema captures both the technical details of the extraction process
    and any analysis metadata provided by the client.
    """

    filename: str = Field(..., description="Original filename of the PDF")
    processing_time: float = Field(..., description="Time taken to process the PDF in seconds")
    page_count: Optional[int] = Field(None, description="Number of pages in the PDF")
    toc_entries: Optional[int] = Field(None, description="Number of table of contents entries")
    headers_strategy: Optional[str] = Field(None, description="Strategy used for header detection (toc/identify)")
    header_levels_detected: Optional[int] = Field(None, description="Number of distinct header levels found")
    margins: Optional[dict[str, int]] = Field(None, description="Margins used for extraction")
    output_path: Optional[str] = Field(None, description="Path where markdown was written (if configured)")
    output_size_chars: Optional[int] = Field(None, description="Size of extracted markdown in characters")
    analysis_results: Optional[dict[str, Any]] = Field(None, description="Analysis metadata from extralit-server")


class ExtractionResponse(BaseModel):
    """
    Response schema for PDF extraction operations.

    Contains the extracted markdown content along with comprehensive metadata
    about the extraction process and results.
    """

    markdown: str = Field(..., description="Extracted markdown content with hierarchical structure")
    metadata: PDFMetadata = Field(..., description="Metadata about the extraction process")
    filename: Optional[str] = Field(None, description="Original filename")
    processing_time: Optional[float] = Field(None, description="Processing time in seconds")


class ErrorResponse(BaseModel):
    """
    Error response schema for failed operations.
    """

    detail: str = Field(..., description="Error message describing what went wrong")
    error_type: Optional[str] = Field(None, description="Type of error that occurred")


class JobStatusResponse(BaseModel):
    """
    Response schema for RQ job status queries.

    Provides comprehensive information about the current state of a background job,
    including progress, timing, and results when available.
    """

    job_id: str = Field(..., description="Unique identifier for the job")
    status: str = Field(..., description="Current job status (queued, started, finished, failed)")
    enqueued_at: Optional[str] = Field(None, description="ISO timestamp when job was enqueued")
    started_at: Optional[str] = Field(None, description="ISO timestamp when job started processing")
    ended_at: Optional[str] = Field(None, description="ISO timestamp when job completed")
    result: Optional[ExtractionResponse] = Field(None, description="Job result if completed successfully")
    error: Optional[str] = Field(None, description="Error message if job failed")
    progress: Optional[dict[str, Any]] = Field(None, description="Progress information if available")


class ExtractionJobRequest(BaseModel):
    """
    Request schema for enqueueing PDF extraction jobs.

    This schema is used when submitting extraction jobs to the RQ queue,
    containing all necessary information for background processing.
    """

    filename: str = Field(..., description="Original filename of the PDF")
    analysis_metadata: Optional[dict[str, Any]] = Field(None, description="Analysis metadata from extralit-server")
    extraction_config: Optional[dict[str, Any]] = Field(None, description="Custom extraction configuration")
    priority: Optional[str] = Field("normal", description="Job priority (low, normal, high)")
    timeout: Optional[int] = Field(600, description="Job timeout in seconds")


class ExtractionJobResponse(BaseModel):
    """
    Response schema for job enqueueing operations.

    Returns the job ID and initial status for tracking the background job.
    """

    job_id: str = Field(..., description="Unique identifier for the enqueued job")
    status: str = Field(..., description="Initial job status")
    queue_name: str = Field(..., description="Name of the queue where job was placed")
    estimated_start_time: Optional[str] = Field(None, description="Estimated time when job will start processing")
