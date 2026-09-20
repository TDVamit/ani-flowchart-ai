# Flowchart AI API

Flowchart AI API is the FastAPI backend for turning natural-language process descriptions into editable, animated, and shareable flowcharts.

## What it does

- Generates a typed multi-screen flowchart specification from a prompt using Anthropic, OpenAI, or Google Gemini.
- Enriches generated elements with Lordicon/Lottie assets through a server-side proxy and one-hour icon caching.
- Stores flowcharts, layouts, parallel views, sharing identifiers, and metadata in MongoDB.
- Provides authenticated flowchart CRUD, public preview links, screen synchronization, and custom asset upload/delete APIs.
- Stores uploaded files in Cloudflare R2 and supports PDF text extraction, audio transcription through OpenAI Whisper, and daily project analysis/reporting.
- Exposes `/health` for a lightweight liveness check and `/docs` for the generated OpenAPI UI.

## Architecture

The API is a FastAPI application started from `main.py`. Its lifespan connects to MongoDB, routers handle authentication and domain APIs, and services isolate LLM, Whisper, R2, report-generation, and context-building concerns. The frontend sends bearer tokens to this API; AI generation returns a normalized chart specification that the frontend imports into its editor.

```text
React/Vite client
        │  JSON + bearer token
        ▼
FastAPI routers ──► MongoDB (charts, projects, entries, reports)
        ├──────────► LLM provider (Anthropic / OpenAI / Gemini)
        ├──────────► Lordicon library (icon inventory + embed resolution)
        ├──────────► Cloudflare R2 (uploaded files and assets)
        └──────────► OpenAI Whisper (audio transcription)
```

## Tech stack

Python 3.13+, FastAPI, Pydantic Settings, Motor/PyMongo, JWT, `anthropic`, `openai`, `google-genai`, boto3, `pypdf`, and Uvicorn.

## Local setup

1. Create a virtual environment and install the pinned requirements:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and replace every placeholder with environment-specific values. Do not commit `.env`.

3. Start MongoDB and configure `MONGODB_URL` and `MONGODB_DB_NAME`.

4. Start the API:

   ```bash
   uvicorn main:app --reload
   ```

The API will be available at the origin you choose for local development. Use `/health` to verify liveness and `/docs` to inspect the contract.

## Configuration

All runtime configuration is read from environment variables via `config.py`. The important groups are:

| Group | Variables | Purpose |
| --- | --- | --- |
| Database | `MONGODB_URL`, `MONGODB_DB_NAME` | MongoDB connection and database name |
| AI | `DEFAULT_LLM_PROVIDER`, `DEFAULT_LLM_MODEL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY` | Provider routing and model credentials |
| Speech | `WHISPER_MODEL`, `OPENAI_API_KEY` | Audio transcription |
| Storage | `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_PUBLIC_URL` | S3-compatible object storage |
| Security | `JWT_SECRET_KEY`, `JWT_EXPIRE_HOURS`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `APP_SECRET_KEY` | Single-user login and token signing |
| Browser access | `CORS_ORIGINS` | Comma-separated frontend origins |

Use long, random secrets in every non-local environment. Supply only the API key for the selected LLM provider, and keep all credentials in the deployment secret manager.

## API surface

- `/api/auth` — login and current-user checks.
- `/api/flowcharts` — authenticated chart CRUD, sharing, parallel views, and screen synchronization; public shared-chart reads are also supported.
- `/api/flowchart-ai/generate` — prompt-to-flowchart generation.
- `/api/flowchart-assets` — custom asset upload, listing, serving, and deletion.
- `/api/lordicon` — server-side library proxy for categories, search, and embed data.
- `/api/files`, `/api/transcription` — protected file and audio workflows.
- `/api/projects`, `/api/entries`, `/api/analysis`, `/api/summary` — project journaling and AI analysis/reporting workflows.
- `/api/settings/models` — models exposed to the client settings UI.

## Deployment

`vercel.json` configures a Vercel Python function entrypoint through `main.py`. A production deployment must provide the same environment variables as `.env.example`, a reachable MongoDB instance, and configured R2/LLM services. Set `CORS_ORIGINS` to the deployed frontend origin instead of relying on a local default.

## Current status

The core flowchart experience is implemented and integrated with the companion frontend. The repository also contains an older/adjacent project analysis subsystem; it is available through its routers but is not required for AI flowchart generation. There is no automated test suite or CI workflow visible in the repository, so deployment validation should include health, authentication, generation, upload, and public-share smoke tests.

## Security notes

- Never place API keys, JWT secrets, database credentials, R2 credentials, or admin passwords in source control or README examples.
- `.env` is ignored by Git; use `.env.example` only as a placeholder contract.
- Review the single-user JWT model before exposing the API to multiple tenants or untrusted public traffic.
