from __future__ import annotations

import io
import os
import time
import hashlib
import logging
from pathlib import Path
from typing import Optional, Tuple
from uuid import UUID

import pymupdf4llm
from fastapi import FastAPI, UploadFile, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse
from .extract import extract_markdown_with_hierarchy, ExtractionConfig

# Import document metadata classes
try:
    from extralit_server.api.schemas.v1.document.metadata import LayoutAnalysisMetadata
    from extralit_server.database import SyncSessionLocal
    from extralit_server.models.database import Document
    HAS_EXTRALIT_SERVER = True
except ImportError:
    HAS_EXTRALIT_SERVER = False


_LOG_LEVEL = "DEBUG" if os.getenv("PDF_ENABLE_LOG_DEBUG", "0") == "1" else "INFO"
logging.basicConfig(level=_LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
LOGGER = logging.getLogger("pdf-markdown-service")

app = FastAPI(
    title="Extralit PDF Markdown Extraction Service",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json",  # can be disabled later if desired
)

# If you ever need CORS for cross-container scenarios (normally unnecessary for internal usage)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1"],
    allow_credentials=False,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "pdf-markdown"}


@app.get("/info")
async def info():
    return {
        "service": "pdf-markdown",
        "pymupdf4llm_version": getattr(pymupdf4llm, "__version__", "unknown"),
    }

def get_document_margins(document_id: UUID) -> tuple[int, int, int, int]:
    """Fetch margins from document metadata in database."""
    default_margins = (0, 50, 0, 30)

    if not HAS_EXTRALIT_SERVER:
        LOGGER.info(f"Extralit server not available, using default margins for {document_id}")
        return default_margins

    try:
        with SyncSessionLocal() as session:
            document = session.query(Document).filter(Document.id == document_id).first()

            if not document or not document.metadata_:
                LOGGER.info(f"No metadata found for document {document_id}, using default margins")
                return default_margins

            analysis_metadata = document.metadata_.get("analysis_metadata", {})
            layout_analysis = analysis_metadata.get("layout_analysis", {})
            margin_analysis = layout_analysis.get("margin_analysis", {})

            if margin_analysis and "estimated_margins" in margin_analysis:
                estimated_margins = margin_analysis["estimated_margins"]

                left = estimated_margins.get("left_px", 0)
                top = estimated_margins.get("top_px", 50)
                right = estimated_margins.get("right_px", 0)
                bottom = estimated_margins.get("bottom_px", 30)

                margins = (left, top, right, bottom)
                LOGGER.info(f"Using document-specific margins for {document_id}: {margins}")
                return margins

    except Exception as e:
        LOGGER.warning(f"Error retrieving margins for document {document_id}: {e}")

    LOGGER.info(f"Using default margins for document {document_id}: {default_margins}")
    return default_margins

@app.post("/extract")
async def extract(pdf: UploadFile) -> JSONResponse:
    try:
        data = await pdf.read()
        markdown, metadata = extract_markdown_with_hierarchy(data, pdf.filename or "document.pdf")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        LOGGER.exception("Unexpected extraction error")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    return JSONResponse(
        {
            "markdown": markdown,
            "metadata": metadata,
            "filename": pdf.filename,
        }
    )

@app.post("/extract_with_document/{document_id}")
async def extract_with_document(
    document_id: UUID,
    pdf: UploadFile
) -> JSONResponse:
    try:
        data = await pdf.read()
        margins = get_document_margins(document_id)
        config = ExtractionConfig(margins=margins)
        markdown, metadata = extract_markdown_with_hierarchy(data, pdf.filename or "document.pdf", config=config)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        LOGGER.exception("Unexpected extraction error")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

    return JSONResponse(
        {
            "markdown": markdown,
            "metadata": metadata,
            "filename": pdf.filename,
            "margins_used": list(margins),
        }
    )
