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
- **File Storage**: S3-compatible storage credentials:
  - `S3_ENDPOINT`
  - `S3_ACCESS_KEY`
  - `S3_SECRET_KEY`

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
- `S3_ENDPOINT` - S3-compatible storage endpoint
- `S3_ACCESS_KEY` - Storage access key
- `S3_SECRET_KEY` - Storage secret key

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

## 🔗 Next Steps

- **Learn More**: [Extralit Documentation](https://docs.extralit.ai/latest/getting_started/quickstart/)
- **Tutorials**: [Hands-on Examples](https://docs.extralit.ai/latest/tutorials/)
- **Advanced Setup**: [HF Spaces Configuration Guide](https://docs.extralit.ai/latest/getting_started/how-to-configure-argilla-on-huggingface/)

## 📄 License

This repository is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0) due to the inclusion of PyMuPDF. The AGPL-licensed components are fully isolated in this package, allowing the main Extralit server to remain Apache-2.0 licensed.