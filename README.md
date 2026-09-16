# GDM Self-Service Data Quality Platform

A self-service data quality platform for [Databricks](https://www.databricks.com/).
Users define data-quality checks against Unity Catalog tables or uploaded CSV files,
deploy them as Databricks jobs, run and schedule them, review results, and optionally
publish results to [OpenMetadata](https://open-metadata.org/).

It runs as **two Databricks Apps** that communicate over HTTP:

- **`backend/`** — a [FastAPI](https://fastapi.tiangolo.com/) REST API (served by uvicorn).
- **`frontend/`** — a [Streamlit](https://streamlit.io/) web UI.

## Features

- Define quality checks (completeness, uniqueness, validity, consistency, …) through a
  guided 4-step wizard — no code required.
- Run checks against Unity Catalog tables or uploaded CSV files.
- Deploy each check set as a Databricks job with one task per check.
- Schedule recurring runs and review historical execution reports.
- Publish results to OpenMetadata.

## Architecture

```
┌──────────────────┐        HTTP (OBO token)        ┌──────────────────┐
│  Streamlit UI    │  ───────────────────────────▶  │  FastAPI backend  │
│  (frontend/)     │        x-user-token header     │  (backend/)       │
└──────────────────┘                                └─────────┬─────────┘
                                                              │
                          ┌───────────────────────────────────┼───────────────────────┐
                          ▼                                     ▼                       ▼
                 Lakebase PostgreSQL              Databricks Jobs / SQL          OpenMetadata
                 (app metadata: projects,         Warehouse (runs checks,        (publish results)
                  jobs, users, executions)         stores results in UC)
```

- **Authentication** uses Databricks on-behalf-of-user (OBO) tokens forwarded from the
  frontend to the backend, plus an Azure Service Principal for SDK operations.
- **App metadata** lives in Lakebase PostgreSQL; **check results** live in Unity Catalog.
- **Jobs** are generated as PySpark notebooks and deployed to the Databricks workspace.

For a deeper walkthrough of the internals, see [CLAUDE.md](CLAUDE.md).

## Getting started

### Prerequisites

- A Databricks workspace with Unity Catalog and [Databricks Apps](https://docs.databricks.com/en/dev-tools/databricks-apps/index.html) enabled.
- A Lakebase PostgreSQL database for application metadata.
- Python 3.10+.
- The [Databricks CLI](https://docs.databricks.com/en/dev-tools/cli/index.html) (for deployment).

### Configuration

Runtime configuration is supplied as Databricks Apps environment variables in each app's
`app.yaml`. Copy the provided examples and fill in your own values:

```bash
cp backend/app.yaml.example  backend/app.yaml
cp frontend/app.yaml.example frontend/app.yaml
```

> **Never commit real secrets.** `app.yaml` and `.env` are git-ignored. Store secrets in
> Databricks secrets / secret-backed environment variables rather than in plaintext.

### Run locally

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000

# Frontend (in a second terminal)
cd frontend
pip install -r requirements.txt
streamlit run app.py
```

Point the frontend at the backend by setting `API_BASE_URL` (defaults to
`http://localhost:8000`).

### Tests

```bash
pip install -r tests/requirements-test.txt
pytest
```

## Deployment

Deploy each app to Databricks Apps with the Databricks CLI:

```bash
databricks sync ./backend  <workspace-path>/backend
databricks apps deploy <backend-app-name>  --source-code-path <workspace-path>/backend

databricks sync ./frontend <workspace-path>/frontend
databricks apps deploy <frontend-app-name> --source-code-path <workspace-path>/frontend
```

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Please also review our
[Code of Conduct](CODE_OF_CONDUCT.md).

## Security

To report a vulnerability, see [SECURITY.md](SECURITY.md). Please do not open public issues
for security reports.

## License

Licensed under the [Apache License 2.0](LICENSE). Third-party dependency licenses are listed
in [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md); see also [NOTICE](NOTICE).
