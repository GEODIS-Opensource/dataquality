# Frontend

Streamlit UI of the Data Quality app, deployed as its own Databricks App. It talks to the
FastAPI backend over HTTP; all business logic, job deployment and storage live in the backend.

See the [root README](../README.md) for the user guide, quality checks, configuration and
deployment.

## Running locally

```bash
cd frontend
pip install -r requirements.txt
API_BASE_URL=http://localhost:8000 streamlit run app.py
```

OBO user tokens only exist inside Databricks Apps; locally the client falls back to the
Databricks SDK / environment credentials.

## Layout

```
app.py               Entry point; redirects to pages/Tool.py
pages/Tool.py        Main page (resolves the user, renders the data quality module)
api_client.py        APIClient: one method per backend endpoint, OBO token forwarding
                     (x-user-token + Authorization), timeouts, SSE deploy stream
config.py            App settings and custom CSS
databricks_utils.py  Current user / workspace detection
data_quality/        Projects, jobs, 4-step workflow, report dashboard (see its README)
components/          Shared UI pieces (header, sidebar, cards)
utils/               Async prefetch and loading placeholders
.streamlit/          Streamlit config
app.yaml             Databricks App definition (template: app.yaml.example)
```

## Configuration

Set in [app.yaml](app.yaml) (start from [app.yaml.example](app.yaml.example)):

| Variable | Purpose |
|---|---|
| `API_BASE_URL` | URL of the backend app |
| `DATABRICKS_SERVER_HOSTNAME`, `DATABRICKS_HTTP_PATH` | Workspace information |
| `STREAMLIT_SERVER_HEADLESS`, `STREAMLIT_SERVER_FILE_WATCHER_TYPE` | Streamlit runtime settings |

`on_behalf_of_user_authentication: true` must stay enabled so the user's token is available to
forward to the backend.
