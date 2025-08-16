"""
Pydantic schemas for the extralit-hf-space API endpoints.
Import schemas from extralit-server to maintain single source of truth.
"""

try:
    # Import all OCR schemas from extralit-server
    from extralit_server.api.schemas.v1.document.ocr import (
        ExtractionRequest,
        ExtractionResponse,
        ErrorResponse
    )
    from extralit_server.api.schemas.v1.document.preprocessing import PDFMetadata
    
except ImportError:
    # Fallback schemas when extralit-server is not available
    from typing import Dict, Any, Optional
    from pydantic import BaseModel, Field
    
    class PDFMetadata(BaseModel):
        """Fallback metadata schema when extralit-server is not available."""
        filename: str
        processing_time: float
        page_count: Optional[int] = None
        language_detected: Optional[list] = None
        processing_settings: Optional[Dict] = None
        analysis_results: Optional[Dict] = None

    class ExtractionRequest(BaseModel):
        """Fallback request schema."""
        file_url: Optional[str] = None
        analysis_metadata: Optional[PDFMetadata] = None
        extraction_config: Optional[Dict[str, Any]] = None

    class ExtractionResponse(BaseModel):
        """Fallback response schema."""
        markdown: str = Field(..., description="Extracted markdown content")
        metadata: PDFMetadata = Field(..., description="Extraction and processing metadata")
        filename: Optional[str] = Field(None, description="Original filename of the PDF")
        processing_time: Optional[float] = Field(None, description="Time taken for extraction in seconds")

    class ErrorResponse(BaseModel):
        """Fallback error response schema."""
        detail: str = Field(..., description="Error message")
        error_code: Optional[str] = Field(None, description="Specific error code")


__all__ = [
    "ExtractionRequest",
    "ExtractionResponse", 
    "ErrorResponse",
    "PDFMetadata",
]
