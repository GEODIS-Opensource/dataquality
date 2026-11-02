# Copyright 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Main Data Quality Page Renderer

This is the entry point for the Data Quality module.
It coordinates the 3-layer architecture:
Layer 1: Projects Management
Layer 2: Jobs Management (for selected project)
Layer 3: Job Configuration Workflow (4 steps)
"""

import streamlit as st
import time
from concurrent.futures import ThreadPoolExecutor
from components.header import render_header
from .session_state import initialize_session_state
from .components import render_progress_indicator
from .steps import (
    render_step1_choose_source,
    render_step2_configure_quality_controls,
    render_step3_deploy_job,
    render_step4_run_schedule
)
from .projects import render_projects_management, save_project_state, get_current_project
from .jobs import render_jobs_management


# Keep this small to avoid thread buildup while still allowing non-blocking autosave.
_AUTOSAVE_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_WORKFLOW_CONTEXT_TTL_SECONDS = 20
_AUTOSAVE_MIN_INTERVAL_SECONDS = 1.5


def _async_save_worker(base_url: str, headers: dict, job_id: int, job_data: dict, timeout: int = 6):
    """Thread-safe background save — no Streamlit API access, uses plain requests."""
    import requests
    import logging
    try:
        response = requests.put(
            f"{base_url}/api/dq/jobs/{job_id}",
            headers=headers,
            json=job_data,
            timeout=timeout
        )
        response.raise_for_status()
        logging.info(f"[AutoSave] ✅ Async save completed for job {job_id}")
    except Exception as e:
        logging.warning(f"[AutoSave] Async save failed for job_id={job_id}: {e}")


def _update_url_params():
    """Update URL query parameters to persist navigation state"""
    params = {}
    view_mode = st.session_state.get('dq_view_mode', 'projects')
    params['view_mode'] = view_mode
    
    if view_mode == 'jobs' or view_mode == 'workflow':
        project_id = st.session_state.get('dq_current_project_id')
        if project_id:
            params['project_id'] = str(project_id)
    
    if view_mode == 'workflow':
        job_id = st.session_state.get('dq_current_job_id')
        if job_id:
            params['job_id'] = str(job_id)
        step = st.session_state.get('dq_step', 1)
        params['step'] = str(step)
    
    st.query_params.update(params)


def render():
    """Main render function for Data Quality page"""
    # Header with brighter blue color
    st.markdown("""
        <div style='display: flex; justify-content: center; align-items: center; margin-top: 2rem;'>
            <h1 style='color: #448aff; font-size: 2.8rem; font-weight: bold; margin-bottom: 0;'>📊 Data Quality (DQ)</h1>
        </div>
        <hr style='margin-top: 1.5rem; margin-bottom: 2rem; border: 1px solid #333;'>
    """, unsafe_allow_html=True)

    # Only show Existing Projects section or jobs management
    initialize_session_state()
    view_mode = st.session_state.get('dq_view_mode', 'projects')
    if view_mode == 'projects':
        render_projects_management()
    elif view_mode == 'jobs':
        project_id = st.session_state.get('dq_current_project_id')
        if project_id:
            project = _get_cached_project(project_id)
            if project:
                render_jobs_management(project_id, project.get('name', 'Project'))
            else:
                st.error("Failed to load project details")
                st.session_state['dq_view_mode'] = 'projects'
                st.rerun()
        else:
            st.error("No project selected")
            st.session_state['dq_view_mode'] = 'projects'
            st.rerun()
    elif view_mode == 'workflow':
        _render_workflow_with_job()


_STEP_DESCRIPTIONS = {
    1: "Select the data source to run quality checks on.",
    2: "Select and configure the quality checks to apply to your dataset.",
    3: "Enable controls and deploy this data quality job to Databricks.",
    4: "Run your job on demand or set up a recurring schedule.",
}

_STEP_RENDERERS = {
    1: lambda: render_step1_choose_source(),
    2: lambda: render_step2_configure_quality_controls(),
    3: lambda: render_step3_deploy_job(),
    4: lambda: render_step4_run_schedule(),
}


def _parse_raw_source_config(raw) -> dict:
    """Parse source_config from a JSON string or return the dict as-is."""
    import json
    if not isinstance(raw, str):
        return raw if isinstance(raw, dict) else {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _restore_source_config_from_job(job: dict) -> None:
    """Restore source config session-state keys from the job record (skip if already set)."""
    import logging
    if st.session_state.get('dq_source_config'):
        return
    logger = logging.getLogger('dq_restore')
    sc = _parse_raw_source_config(job.get('source_config', {}))
    logger.info(f"[RESTORE] source_config from job: type={type(sc)}, keys={list(sc.keys()) if isinstance(sc, dict) else 'N/A'}")
    if not sc:
        logger.warning("[RESTORE] source_config from job is empty!")
        return
    st.session_state['dq_source_type']   = sc.get('source_type')
    st.session_state['dq_catalog']       = sc.get('catalog')
    st.session_state['dq_schema']        = sc.get('schema')
    st.session_state['dq_table']         = sc.get('table')
    st.session_state['dq_dbfs_path']     = sc.get('volume_path')
    st.session_state['dq_file_name']     = sc.get('file_name')
    st.session_state['dq_dataset_name']  = sc.get('dataset_name')
    nested = sc.get('source_config') or {}
    st.session_state['dq_source_config'] = nested if nested else sc
    stored = st.session_state['dq_source_config']
    has_cols = bool(stored.get('columns')) if isinstance(stored, dict) else False
    logger.info(f"[RESTORE] Set dq_source_config: has_columns={has_cols}")


def _fetch_fresh_source_config(job_id: int) -> dict:
    """Fallback: fetch source_config directly from the API when the cached job is stale."""
    import logging
    logger = logging.getLogger('dq_restore')
    logger.warning("[RESTORE] job object has no source_config, fetching fresh from API...")
    from api_client import get_api_client
    result = get_api_client().get_job_details(job_id)
    if result.get('status') != 'success':
        return {}
    fresh_job = result.get('job', result.get('data', {}))
    sc = _parse_raw_source_config(fresh_job.get('source_config', {}))
    logger.info(f"[RESTORE] Fresh API returned source_config: {bool(sc)}")
    return sc


def _apply_csv_preview_restore(columns: list) -> None:
    """Set dq_dataset_preview for a CSV source (column-names-only DataFrame)."""
    import pandas as pd
    if columns:
        st.session_state['dq_dataset_preview'] = pd.DataFrame(columns=columns)
        st.session_state['dq_df_columns_cache'] = columns
    else:
        st.session_state['dq_dataset_preview'] = pd.DataFrame()


def _apply_uc_preview_restore(sc: dict, columns: list) -> None:
    """Set dq_dataset_preview and UC connection keys for a Unity Catalog source."""
    import pandas as pd
    catalog = sc.get('catalog', '')
    schema  = sc.get('schema', '')
    table   = sc.get('table', '')
    st.session_state['dq_unity_catalog'] = catalog
    st.session_state['dq_unity_schema']  = schema
    st.session_state['dq_unity_table']   = table
    st.session_state['dq_dataset_name']  = f"{catalog}.{schema}.{table}"
    if columns:
        st.session_state['dq_dataset_preview'] = pd.DataFrame(columns=columns)
        st.session_state['dq_df_columns_cache'] = columns
    else:
        st.session_state['dq_dataset_preview'] = pd.DataFrame()


def _apply_preview_from_sc(sc: dict) -> None:
    """Build the dataset preview from a resolved source-config dict."""
    import logging, pandas as pd
    logger = logging.getLogger('dq_restore')
    nested      = sc.get('source_config') or {}
    source_type = sc.get('source_type') or nested.get('source_type') or st.session_state.get('dq_source_type')
    columns     = nested.get('columns') or sc.get('columns', [])
    logger.info(f"[RESTORE] Building preview: source_type={source_type}, columns_count={len(columns)}")

    if not st.session_state.get('dq_source_config'):
        st.session_state['dq_source_config'] = nested if nested else sc
        st.session_state['dq_source_type']   = source_type
        st.session_state['dq_dataset_name']  = sc.get('dataset_name')

    if source_type == 'csv':
        _apply_csv_preview_restore(columns)
    elif source_type == 'unity_catalog':
        _apply_uc_preview_restore(sc, columns)
    else:
        st.session_state['dq_dataset_preview'] = pd.DataFrame()


def _restore_dataset_preview_if_missing(job: dict, job_id: int) -> None:
    """Restore dq_dataset_preview after a browser refresh when it has been lost."""
    import logging
    logger  = logging.getLogger('dq_restore')
    preview = st.session_state.get('dq_dataset_preview')
    missing = (preview is None or
               (hasattr(preview, 'empty') and preview.empty
                and len(getattr(preview, 'columns', [])) == 0))
    logger.info(f"[RESTORE] preview_missing={missing}, preview_type={type(preview)}, "
                f"preview_cols={len(getattr(preview, 'columns', [])) if preview is not None else 'N/A'}")
    if not missing:
        return
    sc = _parse_raw_source_config(job.get('source_config', {})) or _fetch_fresh_source_config(job_id)
    if sc:
        _apply_preview_from_sc(sc)
    else:
        logger.error("[RESTORE] No source_config found anywhere — preview cannot be restored")


def _restore_job_meta(job: dict) -> None:
    """Restore job name, description, and step from the job record if not already set."""
    if not st.session_state.get('dq_job_name'):
        st.session_state['dq_job_name']        = job.get('job_name', '')
        st.session_state['dq_job_description'] = job.get('job_description', '')
    if not st.session_state.get('dq_step'):
        st.session_state['dq_step'] = job.get('step', 1)


def _on_back_to_jobs() -> None:
    """Button callback: save, then navigate back to the jobs list."""
    _save_job_state(force=True, async_mode=False)
    st.session_state['dq_view_mode'] = 'jobs'
    st.session_state.pop('dq_current_job_id', None)
    pid = st.session_state.get('dq_current_project_id')
    if pid:
        st.query_params.update({'view_mode': 'jobs', 'project_id': str(pid)})
        st.query_params.pop('job_id', None)
        st.query_params.pop('step', None)


def _render_workflow_banner(project: dict, job: dict) -> None:
    """Render the project › job breadcrumb banner with Back button."""
    from data_quality.jobs import _strip_project_prefix
    step_desc       = _STEP_DESCRIPTIONS.get(st.session_state.get('dq_step', 1), "")
    display_job_name = _strip_project_prefix(job.get('job_name', 'Job'), project.get('name', ''))

    nav_col, banner_col = st.columns([1, 6], gap="small")
    with nav_col:
        if st.button("← Back to Jobs", on_click=_on_back_to_jobs, width="stretch"):
            st.rerun()
    with banner_col:
        st.markdown(f"""
            <div style="margin-top: 4px; margin-bottom: 8px;">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
                    <span style="font-size: 0.8rem; background: #1E3A5F; color: #60A5FA; padding: 3px 10px; border-radius: 20px; font-weight: 600; letter-spacing: 0.03em;">{project.get('name', 'Project')}</span>
                    <span style="color: #4B5563; font-size: 0.9rem;">›</span>
                    <span style="font-size: 0.8rem; background: #1A3A2F; color: #34D399; padding: 3px 10px; border-radius: 20px; font-weight: 600; letter-spacing: 0.03em;">{display_job_name}</span>
                </div>
                <p style='opacity: 0.7; margin: 0; font-size: 0.9rem;'>{step_desc}</p>
            </div>
        """, unsafe_allow_html=True)


def _handle_step_change_autosave() -> None:
    """Sync-save when the user moved to a different step, then update the URL."""
    st.session_state.setdefault('dq_previous_step', st.session_state.get('dq_step', 1))
    if st.session_state.dq_previous_step != st.session_state.get('dq_step', 1):
        _save_job_state(force=True, async_mode=False)
        st.session_state.dq_previous_step = st.session_state.dq_step
        _update_url_params()


def _render_workflow_with_job():
    """Render the workflow with job context (Layer 3 — orchestrator)."""
    project_id = st.session_state.get('dq_current_project_id')
    job_id     = st.session_state.get('dq_current_job_id')

    if not project_id or not job_id:
        st.error("No project or job selected")
        st.session_state['dq_view_mode'] = 'projects'
        st.rerun()
        return

    project, job = _get_cached_workflow_context(project_id, job_id)
    if not project or not job:
        st.error("Failed to load project or job details")
        st.session_state['dq_view_mode'] = 'jobs'
        st.rerun()
        return

    # Restore session state from DB after a browser refresh
    _restore_source_config_from_job(job)
    _restore_dataset_preview_if_missing(job, job_id)
    _restore_job_meta(job)

    _render_workflow_banner(project, job)
    st.markdown("---")
    _handle_step_change_autosave()
    render_progress_indicator(st.session_state.get('dq_step', 1))
    st.markdown("---")

    renderer = _STEP_RENDERERS.get(st.session_state.get('dq_step', 1))
    if renderer:
        renderer()

    # Non-blocking autosave with dedupe/throttle keeps UI responsive.
    _save_job_state(force=False, async_mode=True)


def _get_cached_project(project_id):
    """Return project details from short-lived cache to avoid repeated blocking requests."""
    now = time.time()
    cache = st.session_state.get('_dq_project_cache', {})
    cached = cache.get(project_id)
    if cached and (now - cached.get('ts', 0) < _WORKFLOW_CONTEXT_TTL_SECONDS):
        return cached.get('project')

    from api_client import get_api_client
    api_client = get_api_client()
    result = api_client.get_project(project_id)
    if result.get('status') == 'success':
        project = result.get('project', {})
        cache[project_id] = {'project': project, 'ts': now}
        st.session_state['_dq_project_cache'] = cache
        return project
    return None


def _get_cached_workflow_context(project_id, job_id):
    """Return (project, job) using a short-lived cache to speed up step switching reruns."""
    now = time.time()
    cache = st.session_state.get('_dq_workflow_context_cache', {})
    cache_key = f"{project_id}:{job_id}"
    cached = cache.get(cache_key)
    if cached and (now - cached.get('ts', 0) < _WORKFLOW_CONTEXT_TTL_SECONDS):
        return cached.get('project'), cached.get('job')

    from api_client import get_api_client
    api_client = get_api_client()
    project_result = api_client.get_project(project_id)
    job_result = api_client.get_job_details(job_id)
    if project_result.get('status') != 'success' or job_result.get('status') != 'success':
        return None, None

    project = project_result.get('project', {})
    job = job_result.get('job', job_result.get('data', {}))
    cache[cache_key] = {'project': project, 'job': job, 'ts': now}
    st.session_state['_dq_workflow_context_cache'] = cache
    return project, job


def _compute_job_status(current_step: int) -> str:
    """Derive job lifecycle status — never downgrades a deployed job."""
    if st.session_state.get('dq_deployment_result'):
        return 'deployed'
    if current_step >= 2:
        return 'configured'
    return 'draft'


def _build_job_payload(current_step: int, status: str) -> dict:
    """Assemble the full job_data dict from session state, ready for the API."""
    import json
    import logging

    job_data: dict = {'step': current_step, 'status': status}

    # job_name / job_description — only include when set
    if st.session_state.get('dq_job_name', ''):
        job_data['job_name'] = st.session_state['dq_job_name']
    if st.session_state.get('dq_job_description', ''):
        job_data['job_description'] = st.session_state['dq_job_description']

    # Source config — strip None values, sanitise nested dict
    source_config = {k: v for k, v in {
        'source_type': st.session_state.get('dq_source_type'),
        'catalog':     st.session_state.get('dq_catalog'),
        'schema':      st.session_state.get('dq_schema'),
        'table':       st.session_state.get('dq_table'),
        'volume_path': st.session_state.get('dq_dbfs_path'),
        'file_name':   st.session_state.get('dq_file_name'),
        'dataset_name':st.session_state.get('dq_dataset_name'),
        'source_config':st.session_state.get('dq_source_config', {}),
    }.items() if v is not None}

    nested = source_config.get('source_config', {})
    _has_columns = bool(nested.get('columns')) if isinstance(nested, dict) else False
    logging.info(
        f"[AutoSave] source_type={source_config.get('source_type')}, "
        f"nested_keys={list(nested.keys())[:5] if isinstance(nested, dict) else 'N/A'}, "
        f"has_columns={_has_columns}, step={current_step}"
    )
    if not nested:
        logging.warning(f"[AutoSave] ⚠️ Nested source_config is empty! dq_source_config={st.session_state.get('dq_source_config')}")

    # Ensure nested source_config is a clean copy (json.dumps handles quote_char escaping)
    if isinstance(source_config.get('source_config'), dict):
        source_config['source_config'] = source_config['source_config'].copy()

    if source_config:
        job_data['source_config'] = json.dumps(source_config, ensure_ascii=False)

    # Quality config — only include when components are selected
    quality_config = {
        'selected_components': st.session_state.get('dq_selected_components', []),
        'component_configs':   st.session_state.get('dq_component_configs', {}),
        'component_enabled':   st.session_state.get('dq_component_enabled', {}),
        'thresholds':          st.session_state.get('dq_thresholds', {}),
    }
    if quality_config.get('selected_components'):
        job_data['quality_config'] = json.dumps(quality_config, ensure_ascii=False)

    return job_data


def _is_save_needed(force: bool, signature: str, last_signature: str | None,
                    now: float, last_save_ts: float) -> bool:
    """Return False when the save can be skipped (unchanged payload or too soon)."""
    if not force and signature == last_signature:
        return False
    if not force and (now - last_save_ts) < _AUTOSAVE_MIN_INTERVAL_SECONDS:
        return False
    return True


def _dispatch_async_save(api_client, job_id: int, job_data: dict, force: bool) -> None:
    """Submit a background save, skipping if a save is already in-flight."""
    import logging
    in_flight = st.session_state.get('_dq_autosave_future')
    try:
        if in_flight and not in_flight.done() and not force:
            return
    except Exception:
        pass  # Stale Future; proceed with new save.

    # Capture headers in the Streamlit thread — background threads cannot access them.
    try:
        captured_headers = api_client._get_headers()
    except Exception:
        captured_headers = {"Content-Type": "application/json"}

    try:
        future = _AUTOSAVE_EXECUTOR.submit(
            _async_save_worker, api_client.base_url, captured_headers, job_id, job_data
        )
        st.session_state['_dq_autosave_future'] = future
    except Exception as e:
        logging.error(f"[AutoSave] ❌ Failed to queue async save: {e}")


def _dispatch_sync_save(api_client, job_id: int, job_data: dict) -> None:
    """Blocking save — waits for the API response before returning."""
    import logging
    try:
        result = api_client.update_job_quiet(job_id, job_data)
        logging.info(f"[AutoSave] ✅ Sync save for job {job_id}: {result.get('status') if result else 'no response'}")
    except Exception as e:
        logging.error(f"[AutoSave] ❌ Failed to save job state: {e}")


def _save_job_state(force=False, async_mode=True):
    """Save current job configuration to backend (orchestrator)."""
    import logging
    import hashlib
    import json

    job_id = st.session_state.get('dq_current_job_id')
    if not job_id:
        return

    from api_client import get_api_client
    api_client = get_api_client()

    current_step = st.session_state.get('dq_step', 1)
    status = _compute_job_status(current_step)
    job_data = _build_job_payload(current_step, status)

    signature = hashlib.sha256(
        json.dumps(job_data, sort_keys=True, ensure_ascii=False).encode('utf-8')
    ).hexdigest()
    now = time.time()

    if not _is_save_needed(force, signature,
                           st.session_state.get('_dq_last_autosave_signature'),
                           now, st.session_state.get('_dq_last_autosave_ts', 0)):
        return

    st.session_state['_dq_last_autosave_signature'] = signature
    st.session_state['_dq_last_autosave_ts'] = now
    logging.info(f"[AutoSave] Saving job {job_id} at step {current_step} (async={async_mode}, force={force})")

    if async_mode:
        _dispatch_async_save(api_client, job_id, job_data, force)
    else:
        _dispatch_sync_save(api_client, job_id, job_data)

