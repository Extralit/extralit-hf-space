# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Branching & deploy

Trunk-based. **`main` is the trunk and the default branch**; short-lived `feat/*` / `fix/*` / `docs/*`
branches squash-merge into it via PR. There is no `develop` branch and no `releases/**` branches.

This repo builds nothing on its own schedule — it is **dispatch-driven**. The `extralit` monorepo sends a
`repository_dispatch` (`build-hf-space`) carrying `{tag, branch, is_release}`, and
`.github/workflows/build-hf-space.yml`'s `resolve-env` job maps that payload onto a GitHub Environment:

| Dispatch payload | Environment | Image | Deploys to |
| --- | --- | --- | --- |
| `is_release: true` | `production` | `extralit/extralit-hf-space:vX.Y.Z` + `:latest`, amd64+arm64 | `extralit/public-demo` |
| `branch: main` | `staging` | `extralitdev/extralit-hf-space:<tag>` + `:latest`, amd64 | `extralit-dev/develop` |
| `branch: <n>/merge` | `staging` | `extralitdev/extralit-hf-space:pr-<n>`, amd64 | ephemeral `extralit-dev/pr-<n>` |

**`is_release` is the only production signal.** Branch names are not load-bearing — a payload without
`is_release: true` can never reach `production`, whatever branch it names.

Per-environment `DOCKER_REPO`, `EXTRALIT_SERVER_IMAGE`, and `HF_SPACE_ID` live in GitHub Environment
variables, so the workflow never hardcodes a registry or Space ID.

> The Space `extralit-dev/develop` keeps its name despite the branch being retired: it is a Hugging Face
> resource whose OAuth app is pinned to the `extralit-dev-develop.hf.space` callback. Renaming it breaks
> login.

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

Server settings are `pydantic-settings` fields read with `env_prefix = "EXTRALIT_"` (see
`extralit-server/src/extralit_server/settings.py` in the **`Extralit/extralit` monorepo**),
so **every** knob below is spelled `EXTRALIT_*`. There is no unprefixed `S3_ENDPOINT` —
that name is read by nothing.

**Required for Persistence:**
- `EXTRALIT_DATABASE_URL` - PostgreSQL connection string
- `EXTRALIT_S3_ENDPOINT` - S3-compatible storage endpoint
- `EXTRALIT_S3_ACCESS_KEY` - Storage access key
- `EXTRALIT_S3_SECRET_KEY` - Storage secret key
- `EXTRALIT_S3_REGION` - Storage region (optional)

That shared prefix is load-bearing, not cosmetic: `scripts/deploy_pr_space.py` forwards
exactly the `EXTRALIT_*` keys from the `staging` environment onto each preview Space, so
adding a correctly-named secret or variable there is all it takes to reach a preview.
Anything named otherwise is filtered out — deliberately, since that is what keeps
`HF_TOKEN` and `DOCKER_*` off the Space.

**OAuth Integration:** nothing to configure, and nothing forwarded from GitHub. Spaces
declaring `hf_oauth: true` (which `PR_README` in `deploy_pr_space.py` does) get
`OAUTH_CLIENT_ID` / `OAUTH_CLIENT_SECRET` / `OAUTH_SCOPES` injected by Hugging Face at
runtime; `scripts/start.sh` re-exports them as the `OAUTH2_HUGGINGFACE_*` names the server
expects. The one exception is the source Space `extralit-dev/develop`, whose *custom* OAuth
app is pinned to its own callback URL and therefore does not carry over to previews.


**HF Spaces Production (`extralit-hf-space/`):**
```bash
# Automatic deployment via Spaces interface
# Or programmatic deployment:
import extralit as ex
client = ex.Extralit.deploy_on_spaces(api_key="your_hf_token")
```

The HF Space bundle uses the same core `extralit-server` but packages it with all dependencies for zero-configuration deployment.