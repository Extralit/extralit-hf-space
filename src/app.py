from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware


_LOG_LEVEL = "DEBUG" if os.getenv("PDF_ENABLE_LOG_DEBUG", "0") == "1" else "INFO"
logging.basicConfig(level=_LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
LOGGER = logging.getLogger("extralit-hf-space")

app = FastAPI(
    title="Extralit HF Space Interface",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "extralit-hf-space"}


@app.get("/info")
async def info():
    return {
        "service": "extralit-hf-space",
        "description": "Hugging Face Space for Extralit PyMuPDF processing via RQ workers",
        "architecture": "RQ workers only - no direct PyMuPDF endpoints",
    }
