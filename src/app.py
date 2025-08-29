from __future__ import annotations

import io
import os
import time
import hashlib
import logging
from pathlib import Path
from typing import Optional, Tuple

import pymupdf4llm
from fastapi import FastAPI, UploadFile, HTTPException, Request, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse
from .extract import extract_markdown_with_hierarchy, ExtractionConfig


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

class DocumentMargins(BaseModel):
    left: int = 0
    top: int = 50
    right: int = 0
    bottom: int = 30

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

@app.post("/extract_with_margins")
async def extract_with_margins(
    pdf: UploadFile,
    margins: DocumentMargins = Body(...)
) -> JSONResponse:
    try:
        data = await pdf.read()
        config = ExtractionConfig(margins=(margins.left, margins.top, margins.right, margins.bottom))
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
            "margins_used": [margins.left, margins.top, margins.right, margins.bottom],
        }
    )
