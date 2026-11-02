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

"""Step 4: Run or Schedule Job"""

import streamlit as st
import time
import sys
import os
import logging
import concurrent.futures
from datetime import datetime

logger = logging.getLogger(__name__)

_STEP4_CACHE_TTL = 30  # seconds

# ── Shared string constants ──────────────────────────────────────────────────
_BACK_TO_DEPLOY = "← Back to Deploy"
_RUN_NOW_LABEL  = "▶️ Run Now"
_EXECUTION_TIME_LABEL = "Execution Time"


def _get_step4_data(job_id: int, api_client) -> tuple:
    """Fetch job details + execution history sequentially, with 30s TTL cache.

    Both calls are made in the main Streamlit thread so that st.context.headers
    (which holds the OBO bearer token) is accessible.  A previous parallel
    implementation used ThreadPoolExecutor but worker threads cannot access
    st.context.headers (thread-local) or st.session_state reliably, causing 401s.
    """
    now = time.time()
    cache = st.session_state.get('_step4_cache', {})
    if cache.get('job_id') == job_id and now - cache.get('ts', 0) < _STEP4_CACHE_TTL:
        return cache['job_data'], cache['executions']

    prev_cache = st.session_state.get('_step4_cache', {})
    job_data = None
    executions = None  # None = not fetched yet; [] = fetched but empty
    hist_error = None

    # --- job details ---
    try:
        job_result = api_client.get_job_details(job_id)
        if job_result.get('status') == 'success':
            job_data = job_result.get('data', job_result.get('job', {}))
    except Exception as e:
        logger.warning(f"[Step4] get_job_details failed: {e}")

    # --- execution history ---
    try:
        hist_result = api_client.get_execution_history(job_id, 10)
        if hist_result.get('status') == 'success':
            executions = hist_result.get('executions', [])
        else:
            hist_error = hist_result.get('message', 'Unknown error')
            executions = hist_result.get('executions', None)
            logger.warning(f"[Step4] get_execution_history returned error: {hist_error}")
    except Exception as e:
        hist_error = str(e)
        logger.warning(f"[Step4] get_execution_history failed: {e}")

    # Don't overwrite a previously good cache entry with an empty/failed result
    if executions is None and prev_cache.get('job_id') == job_id:
        executions = prev_cache.get('executions', [])
    elif executions is None:
        executions = []

    st.session_state['_step4_cache'] = {
        'job_id': job_id, 'ts': now,
        'job_data': job_data, 'executions': executions,
        'hist_error': hist_error,
    }
    return job_data, executions


def _invalidate_step4_cache():
    """Force next render to re-fetch fresh data."""
    st.session_state.pop('_step4_cache', None)

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from api_client import get_api_client
from data_quality.payload_generator import generate_dq_payload
from data_quality.jobs import _show_job_report


# ── Small pure helpers (keep CC of callers low) ──────────────────────────────

def _parse_last_exec_date(raw_date):
    """Parse an ISO date string to '%Y-%m-%d %H:%M'; returns raw string on failure."""
    if not raw_date:
        return None
    try:
        return datetime.fromisoformat(str(raw_date)).strftime('%Y-%m-%d %H:%M')
    except Exception:
        return str(raw_date)


def _get_exec_dashboard_url(exec_status, exec_id):
    """Fetch dashboard URL for a completed execution; returns None on failure."""
    if exec_status != 'completed' or not exec_id:
        return None
    try:
        api_client = get_api_client()
        dash_result = api_client.get_execution_dashboard(exec_id)
        if dash_result.get('status') == 'success':
            return dash_result.get('dashboard', {}).get('dashboard_url')
    except Exception:
        pass
    return None


def _extract_last_exec_info(executions):
    """Return (status_raw, run_date, exec_id, exec_status, dashboard_url, launched_by)."""
    if not executions:
        return None, None, None, None, None, '—'
    last = executions[0]
    status = last.get('status')
    exec_id = last.get('id')
    run_date = _parse_last_exec_date(last.get('start_time') or last.get('started_at'))
    launched_by = last.get('triggered_by') or last.get('launched_by') or '—'
    dashboard_url = _get_exec_dashboard_url(status, exec_id)
    return status, run_date, exec_id, status, dashboard_url, launched_by


_RUN_STATUS_MAP = {
    'completed': ('✅ Success', '#10B981'),
    'running':   ('🔄 Running', '#3B82F6'),
    'failed':    ('❌ Failed',  '#EF4444'),
}


def _get_status_display(status_raw):
    """Return (label, hex_color) for a run status string."""
    return _RUN_STATUS_MAP.get((status_raw or '').lower(), ('—', '#9CA3AF'))


def _get_schedule_display(job_data):
    """Return (schedule_display_str, trigger_color) derived from job_data."""
    schedule_cron = job_data.get('schedule_cron') if job_data else None
    if not (schedule_cron and str(schedule_cron).strip() and str(schedule_cron).lower() != 'none'):
        return '🔵 Manual', '#6B7280'
    stype = job_data.get('schedule_type_parsed', 'scheduled')
    t = job_data.get('execution_time_parsed')
    d = job_data.get('execution_day_parsed')
    if stype == 'daily' and t:
        return f'📅 Daily {t}', '#10B981'
    if stype == 'weekly' and t and d:
        return f'📅 {d} {t}', '#10B981'
    if stype == 'monthly' and t and d:
        return f'📅 Monthly {d} {t}', '#10B981'
    return '📅 Scheduled', '#10B981'


_OMD_STATUS_DISPLAY = {
    'completed': ('✅', '#10B981', 'Pushed'),
    'submitted': ('⏳', '#F59E0B', 'Submitted'),
    'pending':   ('⏳', '#F59E0B', 'Submitted'),
    'failed':    ('❌', '#EF4444', 'Failed'),
}


def _get_omd_display(job_id):
    """Fetch latest OMD push status for job; returns (icon, color, label)."""
    try:
        api_client = get_api_client()
        omd_res = api_client.get_omd_latest_status(job_id)
        if omd_res.get('status') == 'success':
            raw = (omd_res.get('omd_status') or '').lower()
            return _OMD_STATUS_DISPLAY.get(raw, ('—', '#9CA3AF', '—'))
    except Exception:
        pass
    return '—', '#9CA3AF', '—'


def _format_banner_schedule(job_data, schedule_cron):
    """Format schedule strings from parsed job_data for the banner widget."""
    stype = job_data.get('schedule_type_parsed', 'scheduled')
    t = job_data.get('execution_time_parsed')
    d = job_data.get('execution_day_parsed')
    tz = job_data.get('schedule_timezone', 'UTC')
    logging.info(f"[Step4 Banner] Parsed schedule: {stype}, time: {t}, day: {d}")
    if stype == 'daily' and t:
        return f'Daily at {t}', 'Scheduled', f'Runs every day at {t} ({tz})'
    if stype == 'weekly' and t and d:
        return f'{d} at {t}', 'Scheduled', f'Runs every {d} at {t} ({tz})'
    if stype == 'monthly' and t and d:
        day_suffix = 'th' if 11 <= d <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d % 10, 'th')
        return (
            f'Monthly ({d}{day_suffix}) at {t}',
            'Scheduled',
            f'Runs on day {d} of each month at {t} ({tz})',
        )
    return 'Scheduled 📅', 'Scheduled', f'Custom schedule: {schedule_cron}'


def _build_schedule_display(schedule_cron, db_job_id):
    """Return (schedule_display, schedule_type, schedule_help) for the banner."""
    if not (schedule_cron and str(schedule_cron).strip() and str(schedule_cron).lower() != 'none'):
        return 'Manual 🔵', 'Manual', 'Job runs manually on demand'
    api_client = get_api_client()
    try:
        job_result = api_client.get_job_details(db_job_id)
        if job_result.get('status') == 'success':
            return _format_banner_schedule(job_result.get('job', {}), schedule_cron)
    except Exception as e:
        logging.error(f"[Step4 Banner] Error getting schedule details: {str(e)}")
    return 'Scheduled 📅', 'Scheduled', 'Job is scheduled to run automatically'


def _clear_omd_run_state():
    """Remove all OMD active-run keys from session state."""
    for key in ('omd_active_run_id', 'omd_active_run_url', 'omd_active_run_job_id', 'omd_active_exec_id'):
        st.session_state.pop(key, None)


def _on_omd_completed(api_client, job_id, run_url):
    """Handle a successfully completed OMD publish run."""
    st.success("✅ DQ results published to OpenMetadata successfully.")
    if run_url:
        st.markdown(f"[View OMD job in Databricks →]({run_url})")
    exec_id = st.session_state.get('omd_active_exec_id')
    if exec_id:
        api_client.update_omd_execution_status(job_id, exec_id, 'completed')
    _clear_omd_run_state()


def _on_omd_failed(api_client, job_id, run_url, status_result):
    """Handle a failed OMD publish run."""
    state_msg = status_result.get('state_message') or status_result.get('message') or 'Unknown error'
    st.error(f"❌ OMD publish failed: {state_msg}")
    if run_url:
        st.markdown(f"[View OMD job in Databricks →]({run_url})")
    exec_id = st.session_state.get('omd_active_exec_id')
    if exec_id:
        api_client.update_omd_execution_status(job_id, exec_id, 'failed', error_message=state_msg)
    _clear_omd_run_state()


def _trigger_omd_push_if_configured(api_client, job_id):
    """Auto-trigger OMD push if an FQN is stored in session state."""
    if not st.session_state.get('omd_fqn_value'):
        return
    omd_fqn = st.session_state['omd_fqn_value']
    omd_result = api_client.publish_to_openmetadata(job_id, omd_fqn)
    if omd_result.get('status') in ('submitted', 'success'):
        st.session_state.update({
            'omd_active_run_id':     omd_result.get('run_id', ''),
            'omd_active_run_url':    omd_result.get('run_url', ''),
            'omd_active_run_job_id': job_id,
            'omd_active_exec_id':    omd_result.get('omd_exec_id'),
        })
    else:
        st.session_state['omd_push_status']  = 'error'
        st.session_state['omd_push_message'] = f"❌ OMD push failed: {omd_result.get('message', 'Unknown error')}"


def _on_run_completed(api_client, job_id, run_id, tasks, duration_str):
    """Handle a completed DQ run: display results, save metadata, trigger OMD."""
    st.success("✅ Job completed successfully!")
    if tasks:
        _display_task_status_inline(tasks)
    results = _display_job_results_inline(api_client, job_id, run_id)
    _save_execution_metadata(job_id, run_id, 'completed', results or {}, duration_str)
    _clear_active_run()
    _invalidate_step4_cache()
    _trigger_omd_push_if_configured(api_client, job_id)
    st.session_state['dq_last_run_completed'] = True
    st.rerun()


def _on_run_failed(api_client, job_id, run_id, tasks, result_state, duration_str):
    """Handle a failed DQ run: display error, save metadata, clear run state."""
    st.error(f"❌ Job failed! Result: {result_state or 'FAILED'}")
    if tasks:
        _display_task_status_inline(tasks)
    _save_execution_metadata(job_id, run_id, 'failed', {'result_state': result_state}, duration_str)
    _clear_active_run()
    _invalidate_step4_cache()
    st.rerun()


# ── Main render entry point ───────────────────────────────────────────────────

def render_step4_run_schedule():
    """Step 4: Run or schedule the job"""
    # Check if job was deployed in Step 3
    if 'dq_deployment_result' not in st.session_state or not st.session_state.dq_deployment_result:
        st.warning("⚠️ No job deployed yet. Please complete Step 3 (Deploy) first.")
        if st.button(_BACK_TO_DEPLOY):
            st.session_state.dq_step = 3
            st.rerun()
        return

    # Get deployment info
    deployment_result = st.session_state.dq_deployment_result

    # Get the database job ID (the one to use for API calls)
    job_id = deployment_result.get('db_job_id')
    if not job_id:
        # Fallback: try to get from 'job_id' field (legacy)
        job_id = deployment_result.get('job_id')

    # Get Databricks job ID for display
    databricks_job_id = deployment_result.get('databricks_job_id') or deployment_result.get('job_id')
    job_url = deployment_result.get('job_url', '')

    # Debug info
    if not job_id:
        st.error(f"❌ No job_id found in deployment result. Available keys: {list(deployment_result.keys())}")
        st.json(deployment_result)
        if st.button(_BACK_TO_DEPLOY):
            st.session_state.dq_step = 3
            st.rerun()
        return

    # Fetch job details + execution history in parallel (with TTL cache)
    api_client = get_api_client()
    job_data, executions = _get_step4_data(job_id, api_client)

    # Show a non-blocking warning if history load failed (helps diagnose DB issues)
    hist_error = st.session_state.get('_step4_cache', {}).get('hist_error')
    if hist_error and not executions:
        st.warning(f"⚠️ Could not load execution history: {hist_error}")

    # Display job info in horizontal layout (1 line with 5 columns)
    _render_job_info_horizontal(deployment_result, job_data, executions)

    # Execute Job section - Radio button with conditional sections
    st.markdown("<div style='margin-top:28px;font-size:1.2rem;font-weight:700;color:inherit;'>⚡ Execute Job</div>", unsafe_allow_html=True)
    run_mode = st.radio("Execution Mode", [_RUN_NOW_LABEL, "📅 Schedule"], horizontal=True, key="run_mode_selector")

    st.markdown("")

    if run_mode == _RUN_NOW_LABEL:
        _render_run_now(job_id, databricks_job_id, job_url, job_data)
    else:
        _render_schedule(job_id)

    st.markdown("---")

    # Execution History - Expander with lazy loading
    with st.expander("📊 Execution History", expanded=False):
        _render_execution_history(job_id, executions)

    # Navigation
    _render_navigation()


# ── Job-info card (horizontal, 5-column) ─────────────────────────────────────

def _render_fqn_section(job_id: str, job_data: dict | None) -> None:
    """Render the 'Publish results DQ in OpenMetadata' subsection.

    Extracted to keep _render_job_info_horizontal within complexity budget.

    Args:
        job_id: Databricks job identifier used when persisting the FQN.
        job_data: Job details from API; may be None.
    """
    st.markdown("<div style='margin-top:20px;font-size:1.2rem;font-weight:700;color:inherit;'>📤 Publish results DQ in OpenMetadata</div>", unsafe_allow_html=True)
    st.markdown("<div style='margin-bottom:8px;'></div>", unsafe_allow_html=True)
    # Prefill FQN input; persist only when user clicks 'Save FQN'
    prefill_fqn = st.session_state.get('omd_fqn_value', '') or (job_data or {}).get('omd_fqn') or ''
    omd_fqn_input = st.text_input(
        "Asset FullyQualifiedName (OpenMetadata) :",
        value=prefill_fqn,
        placeholder="starburst-prd01.schema.my_table",
        key="omd_fqn_inline_input",
    )
    st.caption("Enter the fully qualified name of the asset as it appears in the data catalog (OpenMetadata), then click **Save FQN** to save your entry. Leave empty to skip.")
    new_fqn = omd_fqn_input.strip()
    st.session_state['omd_fqn_value'] = new_fqn

    if st.button("Save FQN", key="omd_fqn_save_btn"):
        try:
            api_client = get_api_client()
            res = api_client.update_omd_fqn(job_id, new_fqn)
            if res.get('status') == 'success':
                st.success("FQN saved")
                _invalidate_step4_cache()
            else:
                st.error(f"Failed to save FQN: {res.get('message', 'unknown')}")
        except Exception as e:
            logger.warning(f"[Step4] Failed to persist omd_fqn: {e}")
            st.error("Error saving FQN")


def _render_job_info_horizontal(deployment_result: dict, job_data: dict = None, executions: list = None):
    """Render job information in a single horizontal line with 5 columns.

    Args:
        deployment_result: Deployment result dictionary
        job_data: Job details from API (pre-fetched)
        executions: Pre-fetched execution history list (most recent first)
    """
    with st.container(border=True):
        db_job_id = deployment_result.get('db_job_id')
        job_id = db_job_id or deployment_result.get('job_id')

        if executions is None:
            executions = []

        last_run_status_raw, last_run_date, _, _, _, _ = _extract_last_exec_info(executions)

        if not last_run_status_raw and job_data:
            last_run_status_raw = job_data.get('last_run_status')
        if not last_run_date and job_data:
            last_run_date = _parse_last_exec_date(job_data.get('last_run_at'))

        status_display, status_color = _get_status_display(last_run_status_raw)
        schedule_display, trigger_color = _get_schedule_display(job_data)

        job_id_for_report = job_id
        job_name_for_report = (job_data.get('job_name') if job_data else None) or deployment_result.get('job_name', 'Job')

        _source_type = st.session_state.get('dq_source_type', '')
        _dataset_name = st.session_state.get('dq_dataset_name', '')
        source_display_name = (
            f"{_source_type} — {_dataset_name}" if _source_type and _dataset_name
            else (_dataset_name or _source_type or 'N/A')
        )

        # Header row
        h1, h2, h3, h4, h5 = st.columns([3, 2, 2, 2, 2])
        with h1: st.markdown("<div style='font-size:0.72rem;font-weight:600;color:#6B7280;'>SOURCE</div>", unsafe_allow_html=True)
        with h2: st.markdown("<div style='font-size:0.72rem;font-weight:600;color:#6B7280;'>STATUS</div>", unsafe_allow_html=True)
        with h3: st.markdown("<div style='font-size:0.72rem;font-weight:600;color:#6B7280;'>RUN DATE</div>", unsafe_allow_html=True)
        with h4: st.markdown("<div style='font-size:0.72rem;font-weight:600;color:#6B7280;'>TRIGGER</div>", unsafe_allow_html=True)
        with h5: st.markdown("<div style='font-size:0.72rem;font-weight:600;color:#6B7280;'>Pushed to OpenMetadata</div>", unsafe_allow_html=True)

        st.markdown("<hr style='margin:2px 0 6px 0;border:none;border-top:1px solid #F3F4F6;'>", unsafe_allow_html=True)

        omd_icon, omd_color, omd_label = _get_omd_display(job_id)

        # Values row
        v1, v2, v3, v4, v5 = st.columns([3, 2, 2, 2, 2])
        with v1:
            st.markdown(f"<div style='font-size:0.82rem;color:#9CA3AF;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{source_display_name}</div>", unsafe_allow_html=True)
        with v2:
            st.markdown(f"<div style='font-size:0.82rem;color:{status_color};font-weight:600;white-space:nowrap;'>{status_display}</div>", unsafe_allow_html=True)
        with v3:
            st.markdown(f"<div style='font-size:0.82rem;color:#9CA3AF;white-space:nowrap;'>{last_run_date or '—'}</div>", unsafe_allow_html=True)
        with v4:
            st.markdown(f"<div style='font-size:0.82rem;color:{trigger_color};font-weight:600;white-space:nowrap;'>{schedule_display}</div>", unsafe_allow_html=True)
        with v5:
            st.markdown(f"<div style='font-size:0.82rem;color:{omd_color};font-weight:600;white-space:nowrap;'>{omd_icon} {omd_label}</div>", unsafe_allow_html=True)

        st.markdown("<div style='padding-bottom:8px;'></div>", unsafe_allow_html=True)

    # --- DQ Results + Publish to OpenMetadata section (below card) ---
    st.markdown("<div style='margin-top:20px;font-size:1.2rem;font-weight:700;color:inherit;'>📊 Data Quality Results</div>", unsafe_allow_html=True)
    st.markdown("<div style='margin-bottom:8px;'></div>", unsafe_allow_html=True)
    if st.button("📊 DQ Results", width="stretch", key="dq_summary_btn"):
        _show_job_report({'id': job_id_for_report, 'job_name': job_name_for_report})

    _render_fqn_section(job_id, job_data)


def _render_job_info_banner(deployment_result: dict, schedule_cron: str = None):
    """Display job information banner

    Args:
        deployment_result: Deployment result dictionary
        schedule_cron: Schedule cron expression from job details (None if not scheduled)
    """
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

    db_job_id = deployment_result.get('db_job_id')
    databricks_job_id = deployment_result.get('databricks_job_id') or deployment_result.get('job_id')

    schedule_display, _, schedule_help = _build_schedule_display(schedule_cron, db_job_id)

    with col1:
        st.markdown(f"""
            <div style="
                background-color: #10B98115;
                border-left: 4px solid #10B981;
                padding: 12px 16px;
                border-radius: 6px;
            ">
                <strong>✅ Job Deployed</strong><br/>
                <span style="font-size: 0.9rem; color: #6B7280;">
                    DB ID: {db_job_id or 'N/A'} |
                    Databricks: {databricks_job_id or 'N/A'}
                </span>
            </div>
        """, unsafe_allow_html=True)

    with col2:
        st.metric("Tasks", deployment_result.get('tasks_count', 0))

    with col3:
        st.metric("Trigger", schedule_display, help=schedule_help)

    with col4:
        if deployment_result.get('job_url'):
            st.link_button("🔗 Open in Databricks", deployment_result['job_url'], width="stretch")


_HISTORY_STATUS_MAP = {
    'pending':   ('⏳ Pending',  '#F59E0B'),
    'running':   ('▶️ Running',  '#3B82F6'),
    'completed': ('✅ Success',  '#10B981'),
    'failed':    ('❌ Failed',   '#EF4444'),
}


def _render_execution_history_header():
    """Render the execution history table header."""
    columns = st.columns([1.2, 1.8, 1.8, 1.5, 1.5])
    labels = ('STATUS', 'RUN DATE', 'RUN ID', 'LAUNCHED BY', 'TRIGGER')
    for column, label in zip(columns, labels):
        with column:
            st.markdown(
                f"<div style='font-size:0.72rem;font-weight:600;color:#6B7280;'>{label}</div>",
                unsafe_allow_html=True,
            )
    st.markdown("<hr style='margin:4px 0 8px 0;border-color:#E5E7EB;'>", unsafe_allow_html=True)


def _render_execution_history_row(exec_data: dict):
    """Render one execution history row."""
    run_id = exec_data.get('databricks_run_id', 'N/A')
    status = exec_data.get('status', 'unknown')
    triggered_by = exec_data.get('triggered_by', 'system') or 'system'
    run_date = _parse_last_exec_date(exec_data.get('start_time') or exec_data.get('started_at')) or '—'
    trigger_display, trigger_color = (
        ('📅 Scheduled', '#10B981')
        if 'schedule' in triggered_by.lower()
        else ('🔵 Manual', '#6B7280')
    )
    status_display, status_color = _HISTORY_STATUS_MAP.get(
        status, (status.capitalize(), '#6B7280')
    )

    columns = st.columns([1.2, 1.8, 1.8, 1.5, 1.5])
    values = (
        (status_display, status_color, True),
        (run_date, '#9CA3AF', False),
        (run_id, '#9CA3AF', False),
        (triggered_by, '#9CA3AF', False),
        (trigger_display, trigger_color, True),
    )
    for column, (value, color, bold) in zip(columns, values):
        weight = 'font-weight:600;' if bold else ''
        with column:
            st.markdown(
                f"<div style='font-size:0.82rem;color:{color};{weight}white-space:nowrap;'>{value}</div>",
                unsafe_allow_html=True,
            )


def _render_execution_history(job_id: int, executions: list = None):
    """Display execution history using pre-fetched data where available."""
    if executions is None:
        # Fallback: fetch directly (e.g. when called standalone)
        api_client = get_api_client()
        history_result = api_client.get_execution_history(job_id, limit=10)
        executions = history_result.get('executions', []) if history_result.get('status') == 'success' else []

    if not executions:
        st.info("📋 No executions yet. Run the job to see history.")
        return

    _render_execution_history_header()
    for exec_data in executions[:10]:
        _render_execution_history_row(exec_data)


def _clear_active_run():
    """Remove active run tracking from session state."""
    st.session_state.pop('dq_active_run_id', None)
    st.session_state.pop('dq_active_run_job_id', None)
    st.session_state.pop('dq_active_run_start_ts', None)


def _start_job(job_id: int, job_url: str):
    """Start the Databricks job and store its run_id in session state."""
    api_client = get_api_client()
    with st.spinner("🚀 Launching Databricks job..."):
        result = api_client.run_job(job_id)
    if result.get('status') != 'success':
        st.error(f"❌ Failed to start job: {result.get('message', 'Unknown error')}")
        return
    st.session_state['dq_active_run_id'] = result.get('run_id')
    st.session_state['dq_active_run_job_id'] = job_id
    st.session_state['dq_active_run_start_ts'] = time.time()
    st.toast(f"{_RUN_NOW_LABEL} Job execution started", icon="✅")
    st.rerun()


def _compute_run_duration(status_result: dict) -> str:
    """Compute a human-readable elapsed duration from a run status payload"""
    db_start = status_result.get('start_time')
    db_end = status_result.get('end_time')
    if db_start:
        end_ms = db_end if db_end else int(time.time() * 1000)
        elapsed_s = int((end_ms - db_start) / 1000)
    else:
        elapsed_s = int(time.time() - st.session_state.get('dq_active_run_start_ts', time.time()))
    return f"{elapsed_s // 60}m {elapsed_s % 60}s" if elapsed_s >= 60 else f"{elapsed_s}s"


def _render_run_status_body(api_client, job_id: int, run_id: str, status_result: dict, tasks: list, duration_str: str):
    """Render the section of the polling fragment specific to the current run status"""
    run_status = status_result.get('run_status', 'unknown')
    databricks_state = status_result.get('databricks_state', 'UNKNOWN')
    result_state = status_result.get('result_state')

    if run_status == 'pending':
        st.info("⏳ Job pending — waiting for cluster...")
    elif run_status == 'running':
        st.info(f"▶️ Job running... (`{databricks_state}`)")
        if tasks:
            _display_task_status_inline(tasks)
    elif run_status == 'completed':
        _on_run_completed(api_client, job_id, run_id, tasks, duration_str)
    elif run_status == 'failed':
        _on_run_failed(api_client, job_id, run_id, tasks, result_state, duration_str)
    else:
        st.info(f"⏳ Databricks state: `{databricks_state}` — waiting...")


@st.fragment(run_every=3)
def _render_run_polling_fragment(job_id: int):
    """
    Auto-refreshing fragment that polls Databricks every 3 seconds.
    Uses @st.fragment(run_every=3) so it survives WebSocket reconnections
    and Streamlit reruns — unlike a while+time.sleep() loop.
    """
    run_id = st.session_state.get('dq_active_run_id')
    if not run_id or st.session_state.get('dq_active_run_job_id') != job_id:
        return

    api_client = get_api_client()

    try:
        status_result = api_client.get_run_status_live(job_id, run_id)

        if status_result.get('status') == 'error':
            st.error(f"❌ Error polling status: {status_result.get('message')}")
            return

        tasks = status_result.get('tasks', [])
        duration_str = _compute_run_duration(status_result)
        st.markdown(f"⏱️ **Duration:** {duration_str}")

        _render_run_status_body(api_client, job_id, run_id, status_result, tasks, duration_str)

    except Exception as e:
        st.warning(f"⚠️ Temporary poll error: {str(e)} — retrying...")


@st.fragment(run_every=60)
def _render_omd_polling_fragment(job_id: int):
    """
    Non-blocking fragment that polls the OMD publish run every 60 seconds.
    Shows progress, then success or error with a link to the Databricks run.
    """
    run_id  = st.session_state.get('omd_active_run_id')
    run_url = st.session_state.get('omd_active_run_url', '')

    if not run_id or st.session_state.get('omd_active_run_job_id') != job_id:
        return

    api_client = get_api_client()
    try:
        status_result = api_client.get_run_status_live(job_id, run_id)
        run_status    = status_result.get('run_status', status_result.get('status', 'unknown'))

        if run_status in ('pending', 'running', 'unknown'):
            st.info("📤 Publishing DQ results to OpenMetadata…")
            if run_url:
                st.markdown(f"[View OMD job in Databricks →]({run_url})")
        elif run_status == 'completed':
            _on_omd_completed(api_client, job_id, run_url)
        elif run_status in ('failed', 'error'):
            _on_omd_failed(api_client, job_id, run_url, status_result)

    except Exception as e:
        st.warning(f"⚠️ Could not fetch OMD run status: {str(e)}")
        if run_url:
            st.markdown(f"[View OMD job in Databricks →]({run_url})")


def _display_task_status_inline(tasks: list):
    """Display task status directly (no placeholder needed inside a fragment)."""
    placeholder = st.empty()
    _display_task_status(placeholder, tasks)


def _display_job_results_inline(api_client, job_id: int, run_id: str) -> dict:
    """Fetch and display job results inline (no placeholder needed inside a fragment)."""
    placeholder = st.empty()
    return _display_job_results(api_client, job_id, run_id, placeholder)


def _show_publish_omd_modal(job_id: int, job_data: dict):
    """Show modal dialog to publish latest DQ results to OpenMetadata."""

    @st.dialog("📤 Publish to OpenMetadata", width="large")
    def publish_dialog():
        st.markdown("Enter the OpenMetadata asset FQN, then publish the latest DQ results.")

        prefill = st.session_state.get('omd_fqn_modal_prefill', '') or (job_data or {}).get('omd_fqn') or ''
        omd_fqn = st.text_input(
            "Asset FullyQaulifiedName :",
            value=prefill,
            placeholder="starburst-prd01.schema.my_table",
            key="omd_fqn_modal_input",
        )
        st.caption("Introduce the fully qualified name as it appears in data catalog (Openmetadata) to push the results to associated asset")

        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("❌ Cancel", width="stretch", key="omd_publish_cancel_btn"):
                st.session_state['show_publish_omd_modal'] = False
                st.rerun()
        with col2:
            if st.button("📤 Publish", type="primary", width="stretch",
                         key="omd_publish_confirm_btn", disabled=not omd_fqn.strip()):
                api_client = get_api_client()
                with st.spinner("Publishing to OpenMetadata..."):
                    result = api_client.publish_to_openmetadata(job_id, omd_fqn.strip())

                if result.get("status") == "success":
                    cols_pushed = result.get("columns_pushed", 0)
                    st.session_state['show_publish_omd_modal'] = False
                    st.toast(f"Published to OpenMetadata ({cols_pushed} column(s))", icon="✅")
                    st.rerun()
                else:
                    st.error(f"❌ {result.get('message', 'Publish failed')}")

    publish_dialog()


def _render_run_now(job_id: int, databricks_job_id: str, job_url: str, job_data: dict = None):
    """Render run now section."""
    st.markdown("<div style='margin-top:8px;margin-bottom:6px;font-size:1.0rem;font-weight:700;color:inherit;'>▶️ Run Job Immediately</div>", unsafe_allow_html=True)
    st.markdown("Execute the data quality checks right now and see results in real-time.")

    if st.session_state.pop('dq_last_run_completed', False):
        st.success("✅ Run completed successfully!")

    # Show OMD push error if submission itself failed
    omd_push_status = st.session_state.pop('omd_push_status', None)
    omd_push_message = st.session_state.pop('omd_push_message', None)
    if omd_push_status == 'error':
        st.error(omd_push_message)

    active_run = (
        bool(st.session_state.get('dq_active_run_id')) and
        st.session_state.get('dq_active_run_job_id') == job_id
    )

    col1, col2 = st.columns([4, 2])
    with col1:
        if st.button(_RUN_NOW_LABEL, type="primary", width="stretch",
                     key="run_job_btn", disabled=active_run):
            _start_job(job_id, job_url)
    with col2:
        if job_url:
            st.markdown(f"""<div style="padding-top: 8px;"><a href="{job_url}" target="_blank" style="color: #3B82F6; text-decoration: none; font-size: 0.9rem;">🔗 View in Databricks</a></div>""", unsafe_allow_html=True)

    # Live polling fragment for DQ run
    if active_run:
        _render_run_polling_fragment(job_id)

    # Non-blocking OMD push polling fragment
    omd_active = (
        bool(st.session_state.get('omd_active_run_id')) and
        st.session_state.get('omd_active_run_job_id') == job_id
    )
    if omd_active:
        _render_omd_polling_fragment(job_id)


def _task_sort_key(task: dict) -> int:
    """Sort tasks by the numeric index embedded in task_key (e.g. 'task_0_prepare_input' → 0)."""
    import re
    m = re.match(r'task_(\d+)_', task.get('task_key', ''))
    return int(m.group(1)) if m else 999


def _display_task_status(placeholder, tasks: list):
    """Display task status in a table"""
    with placeholder.container():
        st.markdown("**Task Status:**")

        for task in sorted(tasks, key=_task_sort_key):
            task_key = task.get('task_key', 'Unknown')
            state = task.get('state', 'UNKNOWN')
            result_state = task.get('result_state', 'N/A')

            # Status icon and label
            if state == 'TERMINATED' and result_state == 'SUCCESS':
                icon = '✅'
                color = '#10B981'
                label = 'Success'
            elif state in ['RUNNING', 'PENDING']:
                icon = '▶️'
                color = '#3B82F6'
                label = 'Running'
            elif result_state == 'FAILED' or state == 'TERMINATED' and result_state not in ('SUCCESS', None, 'N/A'):
                icon = '❌'
                color = '#EF4444'
                label = 'Failed'
            else:
                icon = '⏳'
                color = '#6B7280'
                label = 'Pending'

            st.markdown(f"""
                <div style="
                    background-color: {color}15;
                    border-left: 3px solid {color};
                    padding: 8px 12px;
                    margin: 4px 0;
                    border-radius: 4px;
                ">
                    {icon} <strong>{task_key}</strong> - {label}
                </div>
            """, unsafe_allow_html=True)


def _display_job_results(api_client, job_id: int, run_id: str, placeholder):
    """Fetch and display job results - returns results dict for saving"""
    results = {}
    with st.spinner("📊 Fetching results..."):
        output_result = api_client.get_run_output(job_id, run_id)

        if output_result.get('status') == 'success':
            results = output_result.get('results', {})

            placeholder.empty()
        else:
            placeholder.warning("⚠️ Could not fetch results. Check Databricks for details.")

    return results


def _save_execution_metadata(job_id: int, run_id: str, status: str, results: dict, elapsed_time: str):
    """Save execution metadata to session state and database"""
    import logging
    logger = logging.getLogger(__name__)

    execution_metadata = {
        'run_id': run_id,
        'status': status,
        'executed_at': datetime.now().isoformat(),
        'elapsed_time': elapsed_time,
        'results': results
    }

    # Save to session state
    st.session_state['dq_last_execution'] = execution_metadata
    logger.info(f"💾 Saved execution metadata to session state for job {job_id}")

    # Update job's last_run_at in database
    try:
        api_client = get_api_client()
        job_update = {
            'last_run_at': datetime.now().isoformat(),
            'run_count': st.session_state.get('dq_run_count', 0) + 1
        }

        result = api_client.update_job(job_id, job_update)
        if result.get('status') == 'success':
            logger.info(f"✅ Updated last_run_at for job {job_id}")
            st.session_state['dq_run_count'] = job_update['run_count']
        else:
            logger.warning(f"⚠️ Failed to update last_run_at: {result.get('message')}")
    except Exception as e:
        logger.error(f"❌ Error updating last_run_at: {str(e)}")


def _render_last_execution_info():
    """Display last execution information if available"""
    last_execution = st.session_state.get('dq_last_execution')

    if last_execution:
        st.markdown("#### 🏃 Last Execution")

        status = last_execution.get('status', 'unknown')
        if status == 'completed':
            status_color = '#10B981'
            status_icon = '✅'
            status_text = 'Completed Successfully'
        elif status == 'failed':
            status_color = '#EF4444'
            status_icon = '❌'
            status_text = 'Failed'
        else:
            status_color = '#6B7280'
            status_icon = '⏳'
            status_text = status.title()

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.markdown(f"""
                <div style="
                    background-color: {status_color}15;
                    border-left: 4px solid {status_color};
                    padding: 12px;
                    border-radius: 6px;
                ">
                    <strong>{status_icon} {status_text}</strong>
                </div>
            """, unsafe_allow_html=True)

        with col2:
            executed_at = last_execution.get('executed_at', 'N/A')
            if executed_at != 'N/A':
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(executed_at)
                    executed_at = dt.strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    pass
            st.metric("Executed At", executed_at)

        with col3:
            st.metric("Duration", last_execution.get('elapsed_time', 'N/A'))

        with col4:
            run_id = last_execution.get('run_id', 'N/A')
            st.metric("Run ID", run_id)

        # Show results if available
        results = last_execution.get('results', {})
        if results:
            with st.expander("📊 View Last Results", expanded=False):
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Tasks", results.get('tasks_total', 0))
                with col2:
                    st.metric("Passed", results.get('tasks_passed', 0))
                with col3:
                    st.metric("Failed", results.get('tasks_failed', 0))
                with col4:
                    st.metric("Score", results.get('overall_score', 'N/A'))


def _render_schedule(job_id: int):
    """Render schedule section"""
    st.markdown("#### 📅 Schedule Job Execution")
    st.markdown("Set up a recurring schedule for automated data quality monitoring.")

    col1, col2 = st.columns(2)

    with col1:
        schedule_type = st.selectbox("Schedule Type",
                                     ["daily", "weekly", "monthly", "custom"],
                                     key="schedule_type_select",
                                     format_func=lambda x: x.capitalize())

        if schedule_type == "daily":
            execution_time = st.time_input(_EXECUTION_TIME_LABEL, key="daily_time")
            schedule_config = {
                'schedule_type': 'daily',
                'execution_time': execution_time.strftime("%H:%M")
            }

        elif schedule_type == "weekly":
            execution_day = st.selectbox("Day of Week",
                                        ["Monday", "Tuesday", "Wednesday", "Thursday",
                                         "Friday", "Saturday", "Sunday"],
                                        key="weekly_day")
            execution_time = st.time_input(_EXECUTION_TIME_LABEL, key="weekly_time")
            schedule_config = {
                'schedule_type': 'weekly',
                'execution_day': execution_day,
                'execution_time': execution_time.strftime("%H:%M")
            }

        elif schedule_type == "monthly":
            execution_day = st.number_input("Day of Month", min_value=1, max_value=31, value=1, key="monthly_day")
            execution_time = st.time_input(_EXECUTION_TIME_LABEL, key="monthly_time")
            schedule_config = {
                'schedule_type': 'monthly',
                'execution_day': execution_day,
                'execution_time': execution_time.strftime("%H:%M")
            }

        else:  # custom
            cron_expression = st.text_input("Cron Expression",
                                           placeholder="0 0 * * *",
                                           help="Format: minute hour day month dayofweek",
                                           key="cron_expr")
            schedule_config = {
                'schedule_type': 'custom',
                'cron_expression': cron_expression
            }

    with col2:
        timezone = st.selectbox("Timezone",
                               ["UTC", "Europe/Paris", "America/New_York", "Asia/Tokyo"],
                               key="timezone_select")
        schedule_config['timezone'] = timezone

        st.markdown("---")
        st.markdown("**Preview:**")
        if schedule_type == 'custom':
            st.code(schedule_config.get('cron_expression', '0 0 * * *'))
        else:
            preview = _format_schedule_preview(schedule_config)
            st.info(preview)

    st.markdown("---")

    if st.button("📅 Configure Schedule", type="primary", width="stretch", key="schedule_btn"):
        _configure_schedule(job_id, schedule_config)


def _format_schedule_preview(schedule_config: dict) -> str:
    """Format schedule configuration for preview"""
    schedule_type = schedule_config.get('schedule_type')
    execution_time = schedule_config.get('execution_time', '00:00')
    timezone = schedule_config.get('timezone', 'UTC')

    if schedule_type == 'daily':
        return f"⏰ Runs every day at {execution_time} ({timezone})"
    elif schedule_type == 'weekly':
        day = schedule_config.get('execution_day', 'Monday')
        return f"⏰ Runs every {day} at {execution_time} ({timezone})"
    elif schedule_type == 'monthly':
        day = schedule_config.get('execution_day', 1)
        return f"⏰ Runs on day {day} of each month at {execution_time} ({timezone})"
    else:
        return f"⏰ Custom schedule: {schedule_config.get('cron_expression', 'N/A')}"


def _configure_schedule(job_id: int, schedule_config: dict):
    """Configure job schedule"""
    with st.spinner("⚙️ Configuring schedule..."):
        try:
            api_client = get_api_client()
            result = api_client.schedule_job(job_id, schedule_config)

            if result.get('status') == 'success':
                _invalidate_step4_cache()
                st.toast("Schedule configured successfully!", icon="✅")

                # Display schedule info
                with st.expander("📋 Schedule Details", expanded=True):
                    st.json({
                        'cron_expression': result.get('cron_expression'),
                        'timezone': result.get('timezone'),
                        'message': result.get('message')
                    })

                st.info("💡 The job will now run automatically according to the schedule.")

                # Force refresh to update trigger type in banner
                st.info("🔄 Refreshing page to update job information...")
                import time
                time.sleep(1.5)
                st.rerun()
            else:
                st.error(f"❌ Failed to configure schedule: {result.get('message', 'Unknown error')}")

        except Exception as e:
            st.error(f"❌ Error configuring schedule: {str(e)}")
            st.exception(e)


def _render_navigation():
    """Render navigation buttons"""
    if st.button(_BACK_TO_DEPLOY, width="stretch", key="back_to_deploy"):
        st.session_state.dq_step = 3
        st.rerun()
