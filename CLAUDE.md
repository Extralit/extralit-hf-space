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
- Point `EXTRALIT_STORAGE_URL` at an S3-compatible bucket (or leave it unset to use the
  Space's persistent disk)
- Enable persistent storage in Space settings

### Configuration

Server settings are `pydantic-settings` fields read with `env_prefix = "EXTRALIT_"` (see
`extralit-server/src/extralit_server/settings.py` in the **`Extralit/extralit` monorepo**),
so **every** knob below is spelled `EXTRALIT_*`. There is no unprefixed `S3_ENDPOINT` —
that name is read by nothing.

**Required for Persistence:**
- `EXTRALIT_DATABASE_URL` - PostgreSQL connection string
- `EXTRALIT_STORAGE_URL` - root of object storage; every workspace is a prefix under it
- `EXTRALIT_S3_ACCESS_KEY` - Storage access key (pair with the secret, or omit both)
- `EXTRALIT_S3_SECRET_KEY` - Storage secret key (pair with the access key, or omit both)
- `EXTRALIT_S3_REGION` - Storage region (optional)

`EXTRALIT_STORAGE_URL` names the whole root — endpoint, bucket *and* key prefix — not just
the endpoint that `EXTRALIT_S3_ENDPOINT` used to carry:

| URL | Backend |
|---|---|
| unset | disk under `{EXTRALIT_HOME_PATH}/storage`, i.e. `/data/extralit/storage` on a Space |
| `file:///data/extralit/storage` | disk, named explicitly |
| `http://minio:9000/extralit/prod` | MinIO or any S3-compatible endpoint, path-style |
| `https://<ACCOUNT>.r2.cloudflarestorage.com/extralit` | Cloudflare R2 |
| `s3://extralit/prod` | AWS |

A remote URL with no bucket segment is a startup error. Credentials are optional: omit the
key pair and the server falls back to obstore's own chain (IMDSv2, ECS task role, IRSA).

**An unrecognized `EXTRALIT_S3_ENDPOINT` is ignored silently.** Nothing warns; the server
falls back to the local-disk default and serves happily while the operator believes it is
on S3. On a Space with persistent storage that looks like working software until someone
notices the bucket is empty. If you are migrating a Space, rename the secret in the Space
settings UI — no repository tooling can see or fix it for you.

That shared prefix is load-bearing, not cosmetic: `scripts/deploy_pr_space.py` forwards
exactly the `EXTRALIT_*` keys from the `staging` environment onto each preview Space.
Anything named otherwise is filtered out — deliberately, since that is what keeps
`HF_TOKEN` and `DOCKER_*` off the Space.

**`HF_TOKEN` now exists in exactly one place: the `staging` environment.** The
`deploy-space` job carries no HF credential at all — it authenticates via
[Trusted Publishers](https://huggingface.co/docs/hub/en/trusted-publishers), exchanging a
GitHub OIDC token for one scoped to a single Space for ~1h (`HF_OIDC_RESOURCE` +
`permissions: id-token: write`, both in `build-hf-space.yml`). The surviving secret is
there only because `duplicate_space()` **creates** `extralit-dev/pr-N`, and a trusted
publisher can only be registered on a repo that already exists. So it is `extralit-dev`-only
by construction; no stored credential can reach `extralit/public-demo`.

**`deploy-space` deploys by committing, not by restarting.** It rewrites the Space's
`Dockerfile` `FROM` line to the **digest** the `build` job just pushed and commits that; HF
rebuilds on the new commit. Two independent reasons it works this way, and neither is
negotiable:

1. **`POST /api/spaces/…/restart` rejects OIDC tokens with a 401.** A repo publisher grants
   *write access to the repo*; restarting is a runtime operation, not a repo write. Commits
   are what the credential is actually for. (The exchange itself succeeds — a 401 here comes
   from the restart endpoint, not from auth setup. A misconfigured publisher fails earlier and
   differently, as `OIDCError`/`invalid_grant`.)
2. **A digest cannot go stale.** These Spaces are a thin `FROM <pushed image>`; when that
   line was a *tag*, HF reused the base image it had already built and shipped v0.7.0 as
   0.6.1 with a green job. Changed content forces a real rebuild, which is why no
   `factory_reboot` equivalent is needed anymore.

The one trap when editing the job: the `id-token: write` grant belongs on **`deploy-space`,
not at the top of the file** — every job here matches the publisher's repo/branch/workflow
claims, so a workflow-level grant would hand `deploy-pr-space` the ability to mint a
production token.

### Update vs. create — the split that keeps production config alive

Both deploy jobs share `scripts/hf_space.py`, but they are allowed to write different things:

| Path | Operation | May write |
| --- | --- | --- |
| `deploy-space` (prod/staging) | **update** an existing Space | the `Dockerfile` `FROM` line, and nothing else |
| `deploy-pr-space` (previews) | **create**, then update | the full template on create; the `FROM` line thereafter |

**`deploy-space` must never render a template.** `.oauth.yaml` is not in this repo — it lives
only in the Space repos, and its `allowed_workspaces` differ per Space (`public-demo`:
`itn-recalibration`, `extralit`; `develop`: `public`, `test`). Rendering would wipe those and
the README frontmatter, and the Space would still reach `RUNNING` and the job would still go
green — the same silent-wrong-result class the digest pin exists to prevent. It would also
destroy `deploy_pinned_image`'s `after == before` skip branch, putting every no-op redeploy
behind a 45-minute `wait_for_space`.

**Waiting is two steps, and collapsing them re-opens the bug.** `deploy_pinned_image` polls
until it sees a *build* stage before calling `wait_for_space`, because `wait_for_space` returns
at the first non-build poll — which, in the seconds before the Hub schedules the commit's
build, is still the stage from *before* it. Waiting directly would green-light the previous
image. There is nothing cheaper to check: the runtime API reports no revision (`stage`,
`hardware`, `gcTimeout`, `replicas`, `devMode`, `domains`), so an observed build transition is
the only available proof the commit took effect.

**`SLEEPING` counts as success.** It is absent from `SpaceStage` in `huggingface_hub` 1.26.0,
so it arrives as a bare string, and it is where an idle Space sits between deploys
(`gcTimeout` is 48h) — `extralit-dev/develop` is usually in it. It means the build succeeded
and the Space was later garbage-collected, so rejecting it fails a deploy that worked.

`scripts/` is on `sys.path[0]` for anything run as `python scripts/<name>.py`, which is how
`import hf_space` resolves with no packaging. **Never add `scripts/secrets.py`,
`scripts/types.py`, or `scripts/logging.py`** — the same mechanism would shadow those stdlib
modules for `huggingface_hub`'s transitive dependencies.

### `space_template/` and the `__VAR__` placeholder

`space_template/` holds what a *new* Space should contain — `README.md`, `Dockerfile`,
`.oauth.yaml`, and a `manifest.json` listing the files, the variables, and their defaults.
It exists because `duplicate_space` copies **per-Space** config: anyone duplicating
`extralit/public-demo` inherits extralit's `allowed_workspaces`, which are workspaces they do
not have. So overwriting `README.md` and `.oauth.yaml` after creation is required, not tidier.

`manifest.json` deliberately carries no `required_secrets`. That contract lives in the Hub's
`deployment_templates.required_secrets` and is consumed by four routes; a second copy here
has no seeder, and the drift surfaces as a user's Space silently missing a secret.

Placeholders are `__VAR__`, and the alternatives are all worse:

- `{{VAR}}` — an unquoted YAML plain scalar starting with `{` is a flow mapping, so the
  unrendered `.oauth.yaml` would fail pre-commit's `check-yaml` (which runs with no path
  filters).
- `${VAR}` — collides with Dockerfile `ARG`/`ENV` expansion.
- `string.Template.safe_substitute` — unknown placeholders pass through silently, which *is*
  the silent-wipe failure mode.

`__VAR__` is a valid YAML plain scalar and a valid Dockerfile literal, `hf_space.render`
raises on any placeholder it was not given a value for, and the whole thing is a two-line
regex in Python and in TypeScript, with no library either side.

`scripts/check_space_config.py` is what keeps the template from becoming a file that looks
authoritative but is inert: it renders with each live Space's variables and diffs, comparing
parsed YAML rather than bytes and ignoring the `Dockerfile` `FROM` line that CI owns. It is
**report-only and must stay outside any job holding `id-token: write`.**

**Variables and secrets differ here.** Adding an `EXTRALIT_*` environment *variable* is all
it takes to reach a preview — the whole `vars` set is passed through. An `EXTRALIT_*`
*secret* must additionally be named in `build-hf-space.yml`'s `ALL_SECRETS` object. The
workflow no longer passes `toJSON(secrets)`: doing so handed every credential in scope to a
pip-installed dependency so the script could filter it back out, and GitHub's
malicious-workflow detector held every run of the file for manual approval as a result.

**OAuth Integration:** nothing to configure, and nothing forwarded from GitHub. Spaces
declaring `hf_oauth: true` (which `PR_README` in `deploy_pr_space.py` does) get
`OAUTH_CLIENT_ID` / `OAUTH_CLIENT_SECRET` / `OAUTH_SCOPES` injected by Hugging Face at
runtime; `scripts/start.sh` re-exports them as the `OAUTH2_HUGGINGFACE_*` names the server
expects. The one exception is the source Space `extralit-dev/develop`, whose *custom* OAuth
app is pinned to its own callback URL and therefore does not carry over to previews.

`hf_oauth: true` is only half of it. Those injected variables are consumed only if the image
contains `/home/extralit/.oauth.yaml` — `SecuritySettings` falls through to a bare
`OAuth2Settings()` when the file is missing, and `_build_providers({}, [])` returns no
providers, so the server registers nothing and the login button never appears. The file is
put there by the `COPY .oauth.yaml /home/extralit/` line in each Space's own `Dockerfile`,
which is why nothing may replace that file wholesale — only the `FROM` line is rewritten.


**HF Spaces Production (`extralit-hf-space/`):**
```bash
# Automatic deployment via Spaces interface
# Or programmatic deployment:
import extralit as ex
client = ex.Extralit.deploy_on_spaces(api_key="your_hf_token")
```

The HF Space bundle uses the same core `extralit-server` but packages it with all dependencies for zero-configuration deployment.