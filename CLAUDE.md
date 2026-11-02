# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Data quality Self-Service Platform — a Databricks Apps data-quality tool. Users define
data-quality checks against Unity Catalog tables or uploaded CSVs, deploy them as
Databricks jobs, run/schedule them, view reports, and optionally publish results to
OpenMetadata. It runs as **two separate Databricks Apps** that talk over HTTP:

- `backend/` — FastAPI (uvicorn) REST API.
- `frontend/` — Streamlit UI.

`README.md` is the main functional reference (checks, metrics, output tables, API, config).
The other root `.md` files are open-source governance docs (`CONTRIBUTING`, `SECURITY`,
`CODE_OF_CONDUCT`, `THIRD-PARTY-NOTICES`, `OPEN_SOURCE_RELEASE_PLAN`). `frontend/README.md`
gives a short overview of the frontend. `scripts/`, `SBOM/` and
`.github/workflows/sbom-sign.yml` are license-header / SBOM tooling, unrelated to the app.

## Commands

```bash
# Tests (pytest config in pytest.ini; testpaths = tests/)
pip install -r tests/requirements-test.txt
pytest                              # run the tests/ suite
pytest tests/test_functional.py -v  # single file
pytest tests/test_functional.py::test_projects_list_initialization  # single test
pytest --cov                        # with coverage (source = frontend,backend)

# Run locally
cd backend  && pip install -r requirements.txt && uvicorn main:app --port 8000
cd frontend && pip install -r requirements.txt && streamlit run app.py

# Deploy (Databricks CLI — sync to the Workspace, then deploy each App; see README §11.4)
databricks sync ./backend  "<workspace-path>/backend"  --full
databricks sync ./frontend "<workspace-path>/frontend" --full
databricks apps deploy <backend-app>  --source-code-path "<workspace-path>/backend"
databricks apps deploy <frontend-app> --source-code-path "<workspace-path>/frontend"
```

The pytest suite (`tests/`) only covers frontend session-state and caching behaviour with
mocks; the backend and the notebooks have no automated tests.

## Architecture

### Two-app request flow
Streamlit frontend → `frontend/api_client.py` (`APIClient`) → FastAPI backend over HTTP.
The frontend's `API_BASE_URL` (in `frontend/app.yaml`) points at the backend App's URL.
All backend calls go through the single `APIClient` singleton (`get_api_client()`), which
exposes one method per endpoint and centralizes auth headers, timeouts, and error handling.

### Backend layering (`backend/`)
- `main.py` — FastAPI app, CORS, middleware, router registration.
- `api/` — routers (`users`, `projects`, `jobs`, `datasources`), prefix `/api/...`. Services
  are instantiated once at module import (e.g. `job_service = JobService()`).
- `services/` — business logic. Notable: `job_service`, `databricks_deployment_service`
  (creates/deploys Databricks jobs), `notebook_generator` (renders PySpark notebooks from
  templates in `backend/notebooks/*.ipynb` by replacing `{{placeholder}}` tokens),
  `openmetadata_service`, `databricks_dashboard_service`.
- `database/repositories/` — SQL data access (`user`, `project`, `job`, `datasource`).
- `models/schemas.py` — Pydantic request/response models.
- `config/settings.py` — `Settings` (pydantic-settings) read from env vars; `get_settings()`
  singleton.

### Authentication (the tricky part — read before touching auth)
Two distinct identities are in play:

1. **User identity (OBO / on-behalf-of-user).** Enabled via `on_behalf_of_user_authentication: true`
   in both `app.yaml`s. The frontend extracts the user's token from Streamlit context headers
   (`x-forwarded-access-token` / `x-user-token` / `authorization`), caches it in
   `st.session_state`, and forwards it to the backend as the `x-user-token` header (plus
   `Authorization: Bearer`). The backend `log_requests` middleware in `main.py` captures it into
   a `ContextVar` (`_request_token`) — per-async-task, so concurrent requests don't clash.
   `database/connection.py` uses this OBO token (or the auto-injected `PGPASSWORD`) as the
   **Lakebase PostgreSQL password**, opening a fresh connection per request (no pooling).

2. **Service Principal identity (Azure SP).** `config/databricks_auth.py` builds a cached
   `WorkspaceClient` from `ARM_CLIENT_ID/SECRET/TENANT_ID` for SDK operations (job creation,
   catalog listing). It **must** temporarily pop the platform-injected `DATABRICKS_CLIENT_ID/
   SECRET/TOKEN` env vars so the SDK only sees the Azure SP auth method — don't remove that logic.
   If `DQ_PAT_TOKEN` is set, that PAT overrides the SP (temporary fallback in the same file).

### App metadata database
Lakebase **PostgreSQL** (`database/connection.py`, schema `dq_app`) stores projects, jobs,
users, executions, OMD executions. Distinct from the **Unity Catalog** schemas that hold DQ
*results* (`UC_RESULTS_SCHEMA`) and the app volume for CSV uploads (`UC_UPLOAD_VOLUME`).
There are no incremental migrations: `backend/schema.sql` is the Lakebase setup script,
`backend/unity_catalog_setup.sql` provisions the UC schemas/volume/grants, and
`backend/optimize_tables.sql` is periodic Delta maintenance.

### Frontend DQ wizard (`frontend/data_quality/`)
Core feature is a 4-step wizard orchestrated by `data_quality/main.py` (`render()`):
`steps/step1_choose_source.py` (Unity Catalog table or CSV) → `step2_configure_controls.py`
(select/configure checks) → `step3_deploy_job.py` (deploy to Databricks) → `step4_run_schedule.py`
(run + schedule). Session state is centralized in `data_quality/session_state.py`.

Available quality checks are declared **data-first** in `data_quality/config.py` as
`DQ_COMPONENTS` — each entry lists `params` (types: `multiselect`, `select`, `radio`, `slider`,
`text`, with optional `show_if` conditional display). The step-2 configuration UI is generated
automatically from these definitions. **To add a check, add a dict to `DQ_COMPONENTS`** (and a
matching notebook template in `backend/notebooks/` if it needs new PySpark logic) rather than
writing bespoke UI.

### Job deployment & execution
Deploying (`POST /api/dq/jobs/deploy`) generates notebooks, uploads them to the Databricks
Workspace, and creates a Databricks Job with one task per enabled check. The backend streams
progress back as **Server-Sent Events**; `APIClient.deploy_job()` is a generator that yields
each `data: {...}` update. Runs execute on Databricks; results land in the UC results schema and
are read back for reports/dashboards.

## Config & environments
Runtime configuration lives in `backend/app.yaml` and `frontend/app.yaml` as Databricks Apps
env vars (Databricks host, SQL warehouse, PG connection, catalog/schema names, OMD, cluster
config). **prod vs uat** is switched by commenting/uncommenting the paired values in these files
(prod is currently active). Real secrets (`ARM_CLIENT_SECRET`, `OMD_TOKEN`) are injected via
`valueFrom` app resources, but the files still hold real environment values (hosts, IDs,
warehouse paths) — do not paste them into commits, logs, docs, or other outputs. The
`app.yaml` files are listed in `.gitignore` but still tracked; `app.yaml.example` in each app
folder is the sanitized template — keep it in sync when adding env vars.
