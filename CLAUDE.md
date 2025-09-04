# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Hugging Face Spaces Deployment (extralit-hf-space/)

The `extralit-hf-space/` directory (located at the repo root) contains a complete, self-contained deployment bundle for running Extralit on Hugging Face Spaces. This is a separate project that includes everything needed for a one-click deployment.

### Architecture Overview

**Complete Stack Bundle:**
- **Extralit Server**: Full annotation and dataset management platform
- **PDF Text Extraction**: PyMuPDF-powered hierarchical markdown extraction service
- **Search & Analytics**: Bundled Elasticsearch 8.x for full-text search
- **Background Processing**: Redis + RQ workers for async document processing
- **Authentication**: HuggingFace OAuth integration

### Process Architecture

The deployment uses a Procfile-based multi-process setup:

```
elastic: /usr/share/elasticsearch/bin/elasticsearch
redis: /usr/bin/redis-server
worker_high: sleep 30; python -m extralit_server worker --num-workers 2 --queues high
worker_default: sleep 30; python -m extralit_server worker --num-workers 2 --queues default --queues ocr
extralit: sleep 30; /bin/bash start_extralit_server.sh
```

**Process Breakdown:**
- **elastic**: Bundled Elasticsearch service for vector search
- **redis**: Redis service for background job queues
- **worker_high**: High-priority RQ workers (2 processes)
- **worker_default**: Default/OCR RQ workers (2 processes handling both `default` and `ocr` queues)
- **extralit**: Main FastAPI server process

### Key Features

**One-Click Deployment:**
- Deploy directly from HuggingFace Spaces interface
- Pre-configured with sensible defaults
- Automatic OAuth setup for Space owners

**Performance Optimization:**
- RQ workers use preloaded modules (via `extralit_server.jobs.preload`) to eliminate per-job initialization overhead
- Eliminates PostgreSQL async client reinitialization warnings
- Optimized for high-throughput document processing workloads

**Self-Contained Services:**
- Bundled Elasticsearch for semantic search (no external dependencies)
- Redis for reliable background job processing
- Optional external PostgreSQL database for persistence
- Optional S3-compatible storage for file management

### Deployment Options

**Quick Start (Temporary Data):**
- Use HF Spaces internal storage
- Data lost on Space restart
- Good for testing and demos

**Production (Persistent Data):**
- Configure external PostgreSQL database via `EXTRALIT_DATABASE_URL`
- Configure S3-compatible storage via `S3_*` environment variables
- Enable persistent storage in Space settings

### Configuration

**Required for Persistence:**
- `EXTRALIT_DATABASE_URL` - PostgreSQL connection string
- `S3_ENDPOINT` - S3-compatible storage endpoint
- `S3_ACCESS_KEY` - Storage access key
- `S3_SECRET_KEY` - Storage secret key

**OAuth Integration:**
- `OAUTH2_HUGGINGFACE_CLIENT_ID` - HF OAuth app ID
- `OAUTH2_HUGGINGFACE_CLIENT_SECRET` - HF OAuth secret

### Development vs Production

**Local Development (`extralit-server/`):**
```bash
pdm run server-dev        # Server + worker + auto-reload
pdm run worker           # Background workers only
```

**HF Spaces Production (`extralit-hf-space/`):**
```bash
# Automatic deployment via Spaces interface
# Or programmatic deployment:
import extralit as ex
client = ex.Extralit.deploy_on_spaces(api_key="your_hf_token")
```

The HF Space bundle uses the same core `extralit-server` but packages it with all dependencies for zero-configuration deployment.