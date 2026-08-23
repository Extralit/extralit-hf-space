# Extralit HuggingFace Space

[![Deploy to Spaces](https://huggingface.co/datasets/huggingface/badges/raw/main/deploy-to-spaces-lg.svg)](https://huggingface.co/spaces/extralit/public-demo?duplicate=true)

A complete, self-contained Extralit deployment bundle designed for easy deployment on **HuggingFace Spaces**. This package includes everything needed to run Extralit with PDF text extraction capabilities, including bundled Elasticsearch, Redis, and PyMuPDF-powered OCR processing.

## 🚀 Quick Deploy on HuggingFace Spaces

**The recommended way to get started with Extralit** - get up and running in under 5 minutes without maintaining servers or running commands.

### One-Click Deployment

Click the "Deploy to Spaces" button above to create your own Extralit instance. You can use the default values, but for persistent data, you'll need to configure:

#### Required for Data Persistence
- **Persistent Storage**: Set to `SMALL` (otherwise data is lost on Space restart)
- **Database**: `EXTRALIT_DATABASE_URL` - PostgreSQL connection string
- **File Storage** (optional): by default files land on the Space's persistent disk. To use
  S3-compatible storage instead:
  - `EXTRALIT_STORAGE_URL` - the whole storage root, e.g. `https://<ACCOUNT>.r2.cloudflarestorage.com/extralit`
  - `EXTRALIT_S3_ACCESS_KEY`
  - `EXTRALIT_S3_SECRET_KEY`

  Every name must carry the `EXTRALIT_` prefix — the server reads its settings with
  `env_prefix = "EXTRALIT_"`, so an unprefixed `S3_ENDPOINT` is read by nothing.

#### OAuth Configuration
- `OAUTH2_HUGGINGFACE_CLIENT_ID`
- `OAUTH2_HUGGINGFACE_CLIENT_SECRET`

Leave `ADMIN_USERNAME` and `ADMIN_PASSWORD` empty - you'll sign in with your HF account as the Space owner.

### Deploy with Python SDK

Alternatively, deploy programmatically:

```python
import extralit as ex

# Automatically creates and configures your HF Space
authenticated_client = ex.Extralit.deploy_on_spaces(
    api_key="your_hf_token"
)
```

This method automatically:
- Creates a Space at `https://<your-username>-extralit.hf.space`
- Sets up OAuth authentication
- Creates a default workspace
- Returns an authenticated client ready to use

## 📦 What's Bundled

This HF Space package includes a complete Extralit stack:

- **Extralit Server**: Full annotation and dataset management platform
- **PDF Text Extraction**: PyMuPDF-powered hierarchical markdown extraction
- **Search & Analytics**: Elasticsearch 8.x for full-text search
- **Background Processing**: Redis + RQ workers for async tasks
- **Authentication**: HuggingFace OAuth integration

### Architecture

```
extralit-hf-space/
├── extralit_ocr/           # PDF extraction service
│   ├── extract.py          # PyMuPDF markdown extraction
│   ├── jobs.py             # RQ worker jobs
│   └── schemas.py          # API schemas
├── Dockerfile              # Multi-service container
├── Procfile                # Process orchestration
├── scripts/start.sh        # HF Space startup script
└── config/
    └── elasticsearch.yml   # Elasticsearch configuration
```

## 🔧 Configuration

### Environment Variables

The Space automatically configures itself, but you can customize:

#### HuggingFace Integration
- `OAUTH2_HUGGINGFACE_CLIENT_ID` - HF OAuth app ID
- `OAUTH2_HUGGINGFACE_CLIENT_SECRET` - HF OAuth secret
- `OAUTH2_HUGGINGFACE_SCOPE` - OAuth permissions

#### Data Persistence
- `EXTRALIT_DATABASE_URL` - PostgreSQL connection string
- `EXTRALIT_STORAGE_URL` - object storage root: endpoint, bucket and key prefix together.
  `s3://bucket/prefix`, `http(s)://host[:port]/bucket[/prefix]` for MinIO or R2, or
  `file:///path`. Defaults to `/data/extralit/storage` on the Space's persistent disk.
- `EXTRALIT_S3_ACCESS_KEY` - Storage access key (set with the secret key, or omit both)
- `EXTRALIT_S3_SECRET_KEY` - Storage secret key (set with the access key, or omit both)
- `EXTRALIT_S3_REGION` - Storage region (optional)

#### Processing
- `PDF_MARKDOWN_WRITE_DIR` - Directory for extracted markdown files
- `PDF_MARKDOWN_WRITE_MODE` - `overwrite` or `skip` existing files

## 📖 Using Your Extralit Space

### Sign In

1. Navigate to your Space URL: `https://<username>-extralit.hf.space`
2. Click **"Sign in with Hugging Face"**
3. Authorize the application - you'll be logged in as the Space owner

### Create Your First Dataset

**Import from Hugging Face Hub:**
1. In the Home page, click "Import dataset from Hugging Face"
2. Choose a sample dataset or enter a repo ID (e.g., `stanfordnlp/imdb`)
3. Configure fields and questions as needed
4. Give your dataset a name and start importing

**Using the Python SDK:**

```python
import extralit as ex

# Connect to your Space
client = ex.client(
    api_url="https://<username>-extralit.hf.space",
    api_key="your_api_key"  # Found in My Settings
)

# Verify connection
print(client.me)

# Create a dataset
dataset = client.datasets.create(
    name="my_dataset",
    schema=my_schema
)
```

### PDF Processing

The bundled OCR service automatically processes PDF uploads:

- **Hierarchical Extraction**: Uses PyMuPDF to extract structured markdown
- **Header Detection**: Automatically identifies document structure
- **Background Processing**: Large files processed asynchronously via RQ workers

## 🔄 Export & Sync

Export your annotated datasets back to the Hub:

```python
# Load your dataset
dataset = client.datasets(name="my_dataset")

# Export to HuggingFace Hub
dataset.to_hub(repo_id="username/my-annotated-dataset")
```

## 🐳 Local Development

For local development or custom deployments:

```bash
# Clone this repository
git clone https://github.com/extralit/extralit-hf-space.git
cd extralit-hf-space

# Build the container
docker build -t extralit-hf-space .

# Run with docker-compose or standalone
docker run -p 80:80 extralit-hf-space
```

## ⚙️ GitHub Workflows

Three workflows cover this repository. One builds the image and deploys the live Spaces, one boots the container and health-checks it, and one guards the Space configuration.

### Building and deploying (`build-hf-space.yml`)

The monorepo's release pipeline drives this workflow through a `repository_dispatch` of type `build-hf-space`. There is no `push` trigger, so merging to `main` deploys nothing on its own; a manual `workflow_dispatch` always produces a staging build.

**Inputs** arrive in the dispatch `client_payload`:

| Field | Example | Effect |
| --- | --- | --- |
| `tag` | `v0.7.0`, `main` | Docker tag to build and push |
| `branch` | `main`, `214/merge` | Chooses staging or a preview Space |
| `is_release` | `true` / `false` | The only production signal |

**Routing** happens in the `resolve-env` job. Branch names never select production; only `is_release` does, so a stray payload cannot reach the public demo.

| Input | Environment | `:latest` | Platforms | Target Space |
| --- | --- | :---: | --- | --- |
| `is_release=true` | `production` | yes | amd64 + arm64 | `extralit/public-demo` |
| `branch=main` | `staging` | yes | amd64 | `extralit-dev/develop` |
| any other branch | `staging` | no | amd64 | `extralit-dev/pr-N` |
| `workflow_dispatch` | `staging` | per ref | amd64 | per ref |

**Outputs** are a multi-platform image on Docker Hub (`extralit/extralit-hf-space` for production, `extralitdev/extralit-hf-space` for staging) and a one-line commit to the target Space that repoints its `Dockerfile` `FROM` at the **image digest**, not a tag. A re-pushed tag lets HuggingFace reuse a base it has already built, which once shipped v0.7.0 while the Space still served 0.6.1. The job then blocks until the rebuild settles, so a `BUILD_ERROR` fails the run instead of reporting a green deploy.

`deploy-space` carries no HuggingFace credential. It authenticates through [Trusted Publishers](https://huggingface.co/docs/hub/en/trusted-publishers), exchanging a GitHub OIDC token for one scoped to a single Space for an hour. The `id-token: write` grant sits on that job alone, so no other job can mint a production token.

**Configuration** is scoped per GitHub environment:

| Name | Kind | `production` | `staging` |
| --- | --- | --- | --- |
| `HF_SPACE_ID` | variable | `extralit/public-demo` | `extralit-dev/develop` |
| `DOCKER_REPO` | variable | `extralit/extralit-hf-space` | `extralitdev/extralit-hf-space` |
| `EXTRALIT_SERVER_IMAGE` | variable | `extralit/extralit-server` | `extralitdev/extralit-server` |
| `DOCKER_USERNAME` / `DOCKER_PASSWORD` | secret | yes | yes |
| `HF_TOKEN` | secret | none | preview Spaces only |

`HF_TOKEN` survives only on `staging`. Trusted Publishers scope a token to a repository that already exists, and `duplicate_space()` creates `extralit-dev/pr-N` on demand, so preview creation cannot go keyless. Nothing stored anywhere in this repository can reach the production org.

Preview Spaces get more than a retagged image. Duplicating copies files but not secrets or variables, so the job forwards the `staging` environment's `EXTRALIT_*` config onto the new Space and renders `README.md`, `.oauth.yaml`, and the `Dockerfile` from `space_template/`. Without that render the preview would inherit the source Space's workspace allowlist.

### Testing the container (`integration-test.yml`)

Pull requests and pushes touching `extralit_ocr/`, `scripts/`, `config/`, or the `Procfile` build the image and run it. The job waits for `/api/v1/status` to answer, checks the response parses as a JSON object, and probes the workspaces endpoint. It times out after 10 minutes and dumps container logs on failure.

### Guarding the Space config (`space-config.yml`)

Two jobs, neither of which may ever be given `id-token: write`.

`unit-tests` runs `pytest` on any change to `scripts/`, `tests/`, `space_template/`, or `pyproject.toml`. It covers the pure logic that the deploy path depends on: the `FROM` rewrite preserving `COPY .oauth.yaml`, the `EXTRALIT_*` secret filter, and the stage handling that decides whether a Space actually rebuilt.

`drift` runs weekly and on demand. It renders `space_template/` against each live Space and reports the differences, reading anonymously because both Spaces are public. It never writes. The check exists because `.oauth.yaml` lives only in the Space repositories, so a hand edit is invisible to git and a deletion is otherwise unrecoverable.

## 🔗 Next Steps

- **Learn More**: [Extralit Documentation](https://docs.extralit.ai/latest/getting_started/quickstart/)
- **Tutorials**: [Hands-on Examples](https://docs.extralit.ai/latest/tutorials/)
- **Advanced Setup**: [HF Spaces Configuration Guide](https://docs.extralit.ai/latest/getting_started/how-to-configure-argilla-on-huggingface/)

## 📄 License

This repository is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0) due to the inclusion of PyMuPDF. The AGPL-licensed components are fully isolated in this package, allowing the main Extralit server to remain Apache-2.0 licensed.