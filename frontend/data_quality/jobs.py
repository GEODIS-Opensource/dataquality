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
Data Quality Jobs Management (Layer 2)

This page manages jobs within a project:
- List all jobs for the selected project  
- Create new jobs (launches steps workflow)
- Edit/Configure existing jobs
- Delete jobs
- View job details and execution history
"""

import streamlit as st
from datetime import datetime
import sys
import os
import logging
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api_client import get_api_client
from data_quality.session_state import reset_session_state

_UNKNOWN_USER_EMAIL = 'unknown@example.com'

def render_jobs_management(project_id: int, project_name: str):
    """
    Main Jobs Management page for a project (Layer 2)
    Displays all jobs for the project with create/edit/delete actions
    """
    # Get API client
    api_client = get_api_client()

    # Top bar: Back button (left) + New Job button (right)
    col_back, col_spacer, col_new = st.columns([1, 5, 0.6])
    with col_back:
        if st.button("⬅️ All Projects", key="back_to_projects"):
            st.session_state['dq_view_mode'] = 'projects'
            st.session_state.pop('dq_current_project_id', None)
            st.rerun()
    with col_new:
        if st.button("➕ New Job", type="primary", width="stretch", key="create_new_job_btn"):
            st.session_state['show_create_job_form'] = True
            st.rerun()

    # Title
    st.markdown(f"""
        <div style="margin-top: 20px; margin-bottom: 32px;">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
                <span style="font-size: 0.8rem; background: #1E3A5F; color: #60A5FA; padding: 3px 10px; border-radius: 20px; font-weight: 600; letter-spacing: 0.03em;">{project_name}</span>
                <span style="color: #4B5563; font-size: 0.9rem;">›</span>
                <span style="font-size: 1.4rem; font-weight: 700; color: #FAFAFA;">Jobs</span>
            </div>
            <p style='opacity: 0.7; margin: 0; font-size: 0.9rem;'>Create and manage data quality jobs with custom configuration, schedule, and quality controls.</p>
        </div>
    """, unsafe_allow_html=True)

    # Search & Filter
    col_search, col_filter = st.columns([2, 1])
    with col_search:
        search_term = st.text_input("🔍 Search Jobs", placeholder="Search by name or description...")
    with col_filter:
        filter_status = st.selectbox("Filter by status", ["All", "Draft", "Configured", "Deployed"])
    
    # Show job creation form dialog
    if st.session_state.get('show_create_job_form', False):
        _show_create_job_form(project_id, api_client)
    
    # Add spacing
    st.markdown("<div style='margin: 30px 0;'></div>", unsafe_allow_html=True)
    
    # Fetch jobs
    with st.spinner("Loading jobs..."):
        logger.info(f"[JOBS UI] 🔍 Fetching all jobs for project_id={project_id}")
        result = api_client.get_project_jobs(project_id)
        logger.info(f"[JOBS UI] ✅ Jobs fetch response: status={result.get('status')}, jobs_count={len(result.get('jobs', []))}, message={result.get('message', 'N/A')}")
    
    if result.get('status') != 'success':
        logger.error(f"[JOBS UI] ❌ Failed to load jobs: {result.get('message')}")
        st.error(f"❌ Failed to load jobs: {result.get('message')}")
        return
    
    all_jobs = result.get('jobs', [])
    
    logger.info(f"[JOBS UI] 📊 Total jobs fetched: {len(all_jobs)}")
    for job in all_jobs:
        logger.info(f"[JOBS UI]   - Job ID={job.get('id')}, Name={job.get('job_name')}, Status={job.get('status')}")
    
    # Display jobs
    if not all_jobs:
        st.info("💡 No jobs found for this project. Click 'New Job' to get started!")
        return
    
    # Group jobs by status — clean lifecycle: draft → configured → deployed
    deployed_jobs   = [j for j in all_jobs if j.get('status') == 'deployed']
    configured_jobs = [j for j in all_jobs if j.get('status') == 'configured']
    draft_jobs      = [j for j in all_jobs if j.get('status') == 'draft']
    failed_jobs     = [j for j in all_jobs if j.get('status') in ['failed', 'error']]
    all_sorted_jobs = deployed_jobs + configured_jobs + draft_jobs + failed_jobs

    # Apply search filter
    if search_term:
        all_sorted_jobs = [
            j for j in all_sorted_jobs
            if search_term.lower() in (j.get('job_name') or '').lower()
            or search_term.lower() in (j.get('job_description') or '').lower()
        ]

    # Apply status filter
    if filter_status != "All":
        status_map = {"Draft": "draft", "Configured": "configured", "Deployed": "deployed"}
        target_status = status_map.get(filter_status, filter_status.lower())
        all_sorted_jobs = [j for j in all_sorted_jobs if j.get('status') == target_status]

    if not all_sorted_jobs:
        st.info("🔍 No jobs found matching your criteria.")
        return

    for job in all_sorted_jobs:
        _render_job_card(job, project_id, project_name)


def _strip_project_prefix(job_name: str, project_name: str) -> str:
    """Remove project name prefix from job name if present (handles raw and normalized forms)."""
    if not project_name or not job_name:
        return job_name
    # Try raw prefix with underscore separator (most common: "ProjectName_JobName")
    raw_prefix = project_name + "_"
    if job_name.lower().startswith(raw_prefix.lower()):
        stripped = job_name[len(raw_prefix):]
        return stripped if stripped else job_name
    # Try normalized prefix (e.g. "project_name_job_name")
    norm_project = _normalize_name(project_name)
    norm_prefix = norm_project + "_"
    if _normalize_name(job_name).startswith(norm_prefix):
        stripped = job_name[len(norm_prefix):]
        return stripped if stripped else job_name
    # Try with " - " separator
    dash_prefix = project_name + " - "
    if job_name.lower().startswith(dash_prefix.lower()):
        stripped = job_name[len(dash_prefix):]
        return stripped if stripped else job_name
    return job_name


_DAY_ABBR = {
    'Monday': 'Mon', 'Tuesday': 'Tue', 'Wednesday': 'Wed',
    'Thursday': 'Thu', 'Friday': 'Fri', 'Saturday': 'Sat', 'Sunday': 'Sun',
}

_JOB_STATUS_COLORS = {
    'draft': '#F59E0B', 'configured': '#3B82F6',
    'deployed': '#10B981', 'failed': '#EF4444', 'error': '#EF4444',
}
_JOB_STATUS_ICONS = {
    'draft': '📝', 'configured': '⚙️',
    'deployed': '✅', 'failed': '❌', 'error': '❌',
}


def _resolve_run_status_display(raw: str) -> tuple:
    """Return (display_label, hex_color) for a run-status raw string."""
    lower = raw.lower()
    if lower == 'completed':
        return 'Success', '#10B981'
    if lower == 'running':
        return 'Running', '#3B82F6'
    if lower == 'failed':
        return 'Failed', '#EF4444'
    return raw.capitalize(), '#6B7280'


def _resolve_schedule_display(job: dict) -> tuple:
    """Return (display_string, is_scheduled) for the job's schedule_cron."""
    cron = job.get('schedule_cron')
    if cron is None or str(cron).strip() == '' or str(cron).lower() == 'none':
        return 'Manual', False
    stype = job.get('schedule_type_parsed', 'scheduled')
    etime = job.get('execution_time_parsed')
    eday = job.get('execution_day_parsed')
    if stype == 'daily' and etime:
        return f'Daily {etime}', True
    if stype == 'weekly' and etime and eday:
        return f'{_DAY_ABBR.get(eday, eday)} {etime}', True
    if stype == 'monthly' and etime and eday:
        return f'Monthly {eday} {etime}', True
    return 'Scheduled', True


def _render_job_popover_menu(job: dict, job_id: int, project_id: int, databricks_job_id, status: str) -> None:
    """Render the ⋮ popover menu actions for a job card."""
    if st.button("⚙️ Configure", key=f"config_{job_id}", width="stretch"):
        logger.info(f"[JOBS UI] ⚙️ Configure clicked for job_id={job_id}, project_id={project_id}")
        logger.info(f"[JOBS UI] Session state before workflow: view_mode={st.session_state.get('dq_view_mode')}, job_id={st.session_state.get('dq_current_job_id')}, project_id={st.session_state.get('dq_current_project_id')}")
        _load_job_into_workflow(job_id, project_id)
        logger.info(f"[JOBS UI] Called _load_job_into_workflow for job_id={job_id}, project_id={project_id}")
    if st.button("📊 Details", key=f"view_{job_id}", width="stretch"):
        _show_job_details(job)
    if databricks_job_id and status == 'deployed':
        if st.button("▶️ Run", key=f"run_{job_id}", width="stretch"):
            with st.spinner("Starting job..."):
                result = get_api_client().run_job(job_id)
            if result.get('status') == 'success':
                st.success("✅ Job started!")
                st.rerun()
            else:
                st.error(f"❌ Failed to run: {result.get('message')}")
    else:
        st.button("▶️ Run", key=f"run_{job_id}", disabled=True, width="stretch")
    if st.button("🗑️ Delete", key=f"delete_{job_id}", width="stretch"):
        st.session_state[f'confirm_delete_job_{job_id}'] = True
        st.rerun()


def _render_job_delete_confirmation(job_id: int, job_name: str) -> None:
    """Render the inline delete-confirmation block for a job card."""
    st.markdown("---")
    st.warning("⚠️ **Confirm Deletion**")
    st.markdown(f"Are you sure you want to delete job **{job_name}**?")
    col1, col2, _ = st.columns([1, 1, 2])
    with col1:
        if st.button("✅ Yes, Delete", key=f"confirm_yes_{job_id}", type="primary", width="stretch"):
            result = get_api_client().delete_job(job_id)
            if result.get('status') == 'success':
                st.toast(f"Job '{job_name}' deleted!", icon="✅")
                st.session_state.pop(f'confirm_delete_job_{job_id}', None)
                st.rerun()
            else:
                st.error(f"❌ Failed to delete: {result.get('message')}")
    with col2:
        if st.button("❌ Cancel", key=f"confirm_no_{job_id}", width="stretch"):
            st.session_state.pop(f'confirm_delete_job_{job_id}', None)
            st.rerun()


def _render_job_card(job: dict, project_id: int, project_name: str = ""):
    """Render a single job card with all elements contained in a bordered container."""
    job_id = job.get('id')
    job_name = str(job.get('job_name') or 'Unnamed Job')
    display_job_name = _strip_project_prefix(job_name, project_name)
    status = str(job.get('status') or 'unknown')
    databricks_job_id = job.get('databricks_job_id')

    last_run_date = job.get('last_run_at') or job.get('last_run_date') or job.get('last_run_time')
    last_run_status_display, last_run_status_color = _resolve_run_status_display(
        str(job.get('last_run_status') or 'Never run')
    )
    schedule_display, is_scheduled = _resolve_schedule_display(job)
    trigger_color = '#10B981' if is_scheduled else '#6B7280'

    status_color = _JOB_STATUS_COLORS.get(status, '#6B7280')
    status_icon = _JOB_STATUS_ICONS.get(status, '❓')

    # ── Job Card ─────────────────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("""
        <style>
        div[data-testid="stVerticalBlockBorderWrapper"] {
            padding: 0 !important;
            margin-bottom: 8px !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            padding: 0 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div > div[data-testid="stVerticalBlock"] {
            gap: 0 !important;
            padding: 4px 0 6px 0 !important;
        }
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
            padding-top: 0 !important;
            padding-bottom: 0 !important;
            align-self: flex-start !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stButton"],
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stPopover"] {
            margin-top: 0 !important;
            padding-top: 0 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stHorizontalBlock"] div[data-testid="stColumn"] {
            padding-top: 1px !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div > div[data-testid="stVerticalBlock"] > div[data-testid="stMarkdownContainer"],
        div[data-testid="stVerticalBlockBorderWrapper"] > div > div[data-testid="stVerticalBlock"] > div[data-testid="stMarkdown"] {
            margin-top: 0 !important;
            margin-bottom: 0 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stPopover"] {
            padding-right: 6px !important;
        }
        div[data-testid="stPopoverBody"] div[data-testid="stButton"] {
            margin-top: 6px !important;
            padding-top: 0 !important;
        }
        div[data-testid="stPopoverBody"] div[data-testid="stVerticalBlock"] {
            gap: 6px !important;
        }
        div[data-testid="stPopoverBody"] button {
            font-size: 0.75rem !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] button[kind="primary"],
        div[data-testid="stVerticalBlockBorderWrapper"] button[kind="secondary"] {
            height: 30px !important;
            min-height: 30px !important;
            padding: 0 10px !important;
            font-size: 0.8rem !important;
            line-height: 30px !important;
        }
        </style>
        """, unsafe_allow_html=True)

        # ── TOP ROW: Header (left) + Buttons (right) ──────────────────────────────
        col_header, col_buttons = st.columns([0.63, 0.37])
        with col_header:
            st.markdown(f"""
            <div style="padding: 4px 0 4px 8px; display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 0.8rem; background: #1E3A5F; color: #60A5FA; padding: 3px 10px; border-radius: 20px; font-weight: 600; letter-spacing: 0.03em;">{display_job_name}</span>
            </div>
            """, unsafe_allow_html=True)
        with col_buttons:
            btn_spacer, btn_view, btn_menu = st.columns([0.66, 0.255, 0.085])
            with btn_spacer:
                pass
            with btn_view:
                if st.button("📊 DQ Results", key=f"report_{job_id}", width="stretch"):
                    _show_job_report(job)
            with btn_menu:
                with st.popover("⋮", width="stretch"):
                    _render_job_popover_menu(job, job_id, project_id, databricks_job_id, status)

        # ── BOTTOM: metadata + status badge ───────────────────────────────────────
        st.markdown(f"""
        <div style="padding: 0 8px 18px 8px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="display: flex; gap: 24px; align-items: center;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span style="font-size: 0.9rem;">⏰</span>
                        <div>
                            <div style="font-size: 0.58rem; color: #9CA3AF; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;">Last Run</div>
                            <div style="font-size: 0.76rem; color: #6B7280; font-weight: 600; margin-top: 1px;">{datetime.fromisoformat(last_run_date).strftime('%Y-%m-%d %H:%M') if last_run_date else 'Never'}</div>
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span style="font-size: 0.9rem;">📊</span>
                        <div>
                            <div style="font-size: 0.58rem; color: #9CA3AF; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;">Run Status</div>
                            <div style="font-size: 0.76rem; font-weight: 600; color: {last_run_status_color}; margin-top: 1px;">{last_run_status_display}</div>
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span style="font-size: 0.9rem;">🔔</span>
                        <div>
                            <div style="font-size: 0.58rem; color: #9CA3AF; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;">Trigger</div>
                            <div style="font-size: 0.76rem; color: {trigger_color}; font-weight: 600; margin-top: 1px;">{schedule_display}</div>
                        </div>
                    </div>
                </div>
                <span style="background: {status_color}18; color: {status_color}; border: 1px solid {status_color}40; padding: 3px 10px; border-radius: 6px; font-size: 0.65rem; font-weight: 700; letter-spacing: 0.05em; white-space: nowrap;">{status_icon} {status.capitalize()}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Delete confirmation (outside the bordered container)
    if st.session_state.get(f'confirm_delete_job_{job_id}', False):
        _render_job_delete_confirmation(job_id, job_name)


def _submit_create_job_form(project_id: int, api_client, job_name: str, job_description: str) -> None:
    """Validate inputs, create the job via API, and enter workflow mode."""
    if not job_name or not job_name.strip():
        st.error("⚠️ Job name is required!")
        return
    try:
        logger.info("[JOBS UI] 🧹 Resetting session state before creating new job")
        reset_session_state()
        with st.spinner("Creating job..."):
            job_data = {
                "job_name": job_name.strip(),
                "job_description": job_description.strip() if job_description else "",
                "status": "draft",
                "step": 1,
                "deployed_by": st.session_state.get('current_user', _UNKNOWN_USER_EMAIL),
            }
            logger.info(f"[JOBS UI] 🆕 Creating new job for project_id={project_id}, data={job_data}")
            result = api_client.create_project_job(project_id, job_data)
            logger.info(f"[JOBS UI] ✅ Create job response: status={result.get('status')}, job_id={result.get('job_id')}, message={result.get('message', 'N/A')}")

        if result.get('status') == 'success':
            st.session_state['show_create_job_form'] = False
            new_job_id = result.get('job_id')
            logger.info(f"[JOBS UI] ✅ New job created: job_id={new_job_id}, loading into workflow...")
            st.toast(f"Job '{job_name}' created successfully!", icon="✅")
            _load_job_into_workflow(new_job_id, project_id)
            st.rerun()
        else:
            logger.error(f"[JOBS UI] ❌ Failed to create job: {result.get('message')}")
            st.error(f"❌ Failed to create job: {result.get('message')}")
    except Exception as e:
        logger.error(f"[JOBS UI] ❌ Error creating job: {str(e)}")
        st.error(f"❌ Error creating job: {str(e)}")


def _show_create_job_form(project_id: int, api_client):
    """Show modal form to create a new job with name and description."""
    @st.dialog("🆕 New Job", width="large")
    def create_job_dialog():
        st.markdown("#### Define Your New Job")
        st.markdown("Enter a name and description to identify this data quality job.")
        st.markdown("")

        job_name = st.text_input(
            "Job Name *",
            placeholder="e.g., Customer Data Quality Check",
            key="new_job_name_input",
        )
        job_description = st.text_area(
            "Description (optional)",
            placeholder="Brief description of what this job checks...",
            key="new_job_description_input",
            height=120,
        )

        st.markdown("---")
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("❌ Cancel", width="stretch"):
                st.session_state['show_create_job_form'] = False
                st.rerun()
        with col2:
            if st.button("✅ Create Job", width="stretch", type="primary", disabled=not job_name):
                _submit_create_job_form(project_id, api_client, job_name, job_description)

        st.markdown("---")
        st.info(
            "💡 **Tip**: Choose a descriptive name that helps you identify the job later. "
            "You can configure the data source and quality controls in the next steps."
        )

    create_job_dialog()


def _create_new_job(project_id: int, api_client):
    """Create a new job and enter workflow mode"""
    user_email = st.session_state.get('current_user', _UNKNOWN_USER_EMAIL)
    
    # Create job via API
    with st.spinner("Creating new job..."):
        job_data = {
            'job_name': f'New Job {datetime.now().strftime("%Y%m%d_%H%M%S")}',
            'job_description': 'New job',
            'status': 'draft',
            'step': 1,
            'deployed_by': user_email
        }
        logger.info(f"[JOBS UI] 🆕 Creating new job for project_id={project_id}, data={job_data}")
        result = api_client.create_project_job(project_id=project_id, job_data=job_data)
        logger.info(f"[JOBS UI] ✅ Create job response: status={result.get('status')}, job_id={result.get('job_id')}, message={result.get('message', 'N/A')}")
        
        if result.get('status') == 'success':
            job_id = result.get('job_id')
            st.toast("Job created successfully!", icon="✅")
            # Enter workflow mode for this new job
            _load_job_into_workflow(job_id, project_id)
            st.rerun()
        else:
            st.error(f"❌ Failed to create job: {result.get('message')}")


def _set_workflow_mode(job_id: int, project_id: int, job: dict) -> None:
    """Write workflow-mode keys to session state and update URL params."""
    st.session_state['dq_view_mode'] = 'workflow'
    st.session_state['dq_current_job_id'] = job_id
    st.session_state['dq_current_project_id'] = project_id
    st.session_state['dq_in_project_mode'] = True
    st.session_state['dq_step'] = job.get('step', 1)
    st.session_state['dq_job_name'] = job.get('job_name', '')
    st.session_state['dq_job_description'] = job.get('job_description', '')
    st.query_params.update({
        'view_mode': 'workflow',
        'project_id': str(project_id),
        'job_id': str(job_id),
        'step': str(job.get('step', 1)),
    })
    logger.info(f"[JOBS UI] ✅ Set step to: {st.session_state['dq_step']}")


def _restore_workflow_source_config(job: dict) -> None:
    """Parse and restore source config; log nested-config diagnostics."""
    source_config = _parse_json_field(job.get('source_config', {}))
    if not source_config:
        logger.warning("[JOBS UI] ⚠️ No source_config to restore")
        return
    logger.info(f"[JOBS UI] 📦 Source config type: {type(job.get('source_config'))}")
    _restore_source_config_from_url(source_config)
    nested_config = source_config.get('source_config', {})
    if nested_config:
        logger.info(f"[JOBS UI] 📦 Nested source_config has {len(nested_config)} keys: {list(nested_config.keys())[:10]}")
    else:
        logger.warning("[JOBS UI] ⚠️ Nested source_config is empty or missing!")
    logger.info(f"[JOBS UI] ✅ Restored source: type={st.session_state.get('dq_source_type')}, dataset={st.session_state.get('dq_dataset_name')}")


def _restore_workflow_quality_config(job: dict) -> None:
    """Parse and restore quality config into session state."""
    quality_config = _parse_json_field(job.get('quality_config', {}))
    if not quality_config:
        logger.warning("[JOBS UI] ⚠️ No quality_config to restore")
        return
    logger.info(f"[JOBS UI] 📦 Quality config type: {type(job.get('quality_config'))}")
    _restore_quality_config_from_url(quality_config)


def _load_job_into_workflow(job_id: int, project_id: int):
    """Load job configuration into session state and enter workflow mode."""
    from data_quality.session_state import reset_session_state_full
    reset_session_state_full()
    api_client = get_api_client()

    with st.spinner("Loading job configuration..."):
        logger.info(f"[JOBS UI] 📥 Loading job details for job_id={job_id}")
        result = api_client.get_job_details(job_id)
        logger.info(f"[JOBS UI] ✅ Get job details response: status={result.get('status')}, message={result.get('message', 'N/A')}")

        if result.get('status') != 'success':
            st.error(f"❌ Failed to load job: {result.get('message')}")
            return

        # Backend returns 'data' not 'job'
        job = result.get('data', result.get('job', {}))
        logger.info(f"[JOBS UI] 📦 Job data received: step={job.get('step')}, name={job.get('job_name')}")

        _set_workflow_mode(job_id, project_id, job)
        _restore_workflow_source_config(job)
        _restore_workflow_quality_config(job)
        _restore_deployment_config_from_url(_parse_json_field(job.get('deployment_config', {})), job, job_id)

        run_count = job.get('run_count', 0)
        if run_count:
            st.session_state['dq_run_count'] = run_count
            logger.info(f"[JOBS UI] 🎯 Restored run count: {run_count}")

        logger.info(f"[JOBS UI] 📊 Final loaded state: step={st.session_state['dq_step']}, components={len(st.session_state.get('dq_selected_components', []))}")
        st.rerun()


def _resolve_job_input_source(job: dict) -> str:
    """Return a human-readable input source label for the job, or empty string."""
    source_config = _parse_json_field(job.get('source_config', {}))
    source_type = source_config.get('source_type')
    if source_type == 'csv':
        nested = source_config.get('source_config') if isinstance(source_config.get('source_config'), dict) else {}
        dataset_name = (
            nested.get('dataset_name')
            or source_config.get('dataset_name')
            or source_config.get('file_name')
            or 'None'
        )
        return dataset_name
    if source_type == 'unity_catalog':
        return f"{source_config.get('catalog', '')}.{source_config.get('schema', '')}.{source_config.get('table', '')}"
    return ''


def _format_job_date(iso_str) -> str:
    """Return a formatted date string or 'N/A'."""
    if not iso_str:
        return 'N/A'
    return datetime.fromisoformat(iso_str).strftime('%Y-%m-%d %H:%M')


def _render_job_details_content(job: dict) -> None:
    """Render all content inside the job-details modal."""
    # Description
    st.markdown("### 📝 Description")
    st.write(job.get('job_description', 'No description'))
    st.markdown("---")

    # Information columns
    st.markdown("### ℹ️ Information")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Job Name:** {job.get('job_name', 'N/A')}")
        input_source = _resolve_job_input_source(job)
        if input_source:
            st.markdown(f"**Input source:** {input_source}")
        st.markdown(f"**Status:** {job.get('status', 'N/A').upper()}")
        st.markdown(f"**Created:** {_format_job_date(job.get('created_at'))}")
    with col2:
        st.markdown(f"**Deployed By:** {job.get('deployed_by', 'N/A')}")
        modified_raw = job.get('last_modified') or job.get('updated_at')
        st.markdown(f"**Modified:** {_format_job_date(modified_raw)}")
        st.markdown(f"**Databricks Job ID:** {job.get('databricks_job_id', 'Not deployed yet')}")

    st.markdown("---")

    # Configs (raw JSON)
    if job.get('source_config'):
        st.markdown("### 🗄️ Source Configuration")
        st.json(job.get('source_config'))
    if job.get('quality_config'):
        st.markdown("### ✅ Quality Configuration")
        st.json(job.get('quality_config'))

    if st.button("Close", width="stretch"):
        st.rerun()


def _show_job_details(job: dict):
    """Show job details in a modal dialog."""
    @st.dialog(f"Job Details: {job.get('job_name', 'Unnamed')}", width="large")
    def show_details_modal():
        _render_job_details_content(job)

    show_details_modal()


def _normalize_name(name: str) -> str:
    """Normalize a project/job name for table naming.

    Must mirror sanitize_name() used in every Databricks notebook so that
    table-name lookups match what the notebooks wrote:
        re.sub(r'[^a-zA-Z0-9_]', '_', name).lower()
    """
    import re
    return re.sub(r'[^a-zA-Z0-9_]', '_', name).lower()


def _create_score_card(check_type: str, score: float, status: str, faulty_count: int = 0) -> str:
    """Modern score card: white background, left accent border, colored score"""
    status_upper = (status or '').upper()
    if status_upper == 'OK':
        accent   = '#10B981'
        bg_badge = '#D1FAE5'
        fg_badge = '#065F46'
        status_label = '✅ OK'
    elif status_upper == 'WARNING':
        accent   = '#F59E0B'
        bg_badge = '#FEF3C7'
        fg_badge = '#92400E'
        status_label = '⚠️ WARNING'
    else:
        accent   = '#EF4444'
        bg_badge = '#FEE2E2'
        fg_badge = '#991B1B'
        status_label = '❌ KO'

    # Progress bar width capped at 100
    bar_pct = min(score, 100)

    check_icons = {
        'completeness':  '🔍',
        'consistency':   '🔗',
        'comparaison':   '⚖️',
        'validity':      '✔️',
        'uniqueness':    '🔑',
        'timeliness':    '🕐',
    }
    icon = check_icons.get(check_type.lower(), '📋')

    return f"""
    <div style="
        background: var(--background-color);
        border: 1px solid rgba(128,128,128,0.2);
        border-left: 4px solid {accent};
        border-radius: 10px;
        padding: 1rem 1.1rem 0.9rem 1.1rem;
        margin-bottom: 0.75rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    ">
        <!-- Check type label -->
        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:0.6rem;">
            <div style="font-size:0.72rem; font-weight:700; color:#9CA3AF;
                        text-transform:uppercase; letter-spacing:0.07em;">
                {icon} {check_type}
            </div>
            <span style="background:{bg_badge}; color:{fg_badge};
                         font-size:0.62rem; font-weight:700;
                         padding:2px 7px; border-radius:20px;
                         letter-spacing:0.03em; white-space:nowrap;
                         display:inline-flex; align-items:center; gap:2px;">
                {status_label}
            </span>
        </div>
        <!-- Big score -->
        <div style="font-size:2.4rem; font-weight:750; color:{accent}; line-height:1;">
            {score:.1f}<span style="font-size:1rem; color:#9CA3AF;">%</span>
        </div>
        <!-- Progress bar -->
        <div style="background:var(--secondary-background-color); border-radius:4px; height:5px; margin:0.55rem 0 0.65rem 0;">
            <div style="background:{accent}; width:{bar_pct}%; height:100%; border-radius:4px;"></div>
        </div>
        <!-- Faulty records -->
        <div style="font-size:0.72rem; color:#9CA3AF; padding-top:0.1rem;">
            Faulty records : <span style="font-weight:700; color:{accent if faulty_count == 0 else '#EF4444'};">{faulty_count:,}</span>
        </div>
    </div>
    """


def _fetch_project_name(api_client, project_id: int) -> str:
    """Return the project name or 'Unknown' if unavailable."""
    if not project_id:
        return "Unknown"
    result = api_client.get_project(project_id)
    if result.get('status') == 'success':
        return result.get('project', {}).get('name', 'Unknown')
    return "Unknown"


def _fetch_latest_dashboard_url(api_client, job_id: int):
    """Return the dashboard URL of the latest completed execution, or None."""
    try:
        history_result = api_client.get_execution_history(job_id, limit=1)
        if history_result.get('status') != 'success':
            return None
        executions = history_result.get('executions', [])
        if not executions or executions[0].get('status') != 'completed':
            return None
        last_exec_id = executions[0].get('id')
        if not last_exec_id:
            return None
        dash_result = api_client.get_execution_dashboard(last_exec_id)
        if dash_result.get('status') == 'success':
            return dash_result.get('dashboard', {}).get('dashboard_url')
    except Exception:
        pass
    return None


def _compute_avg_score_style(avg_score: float) -> tuple:
    """Return (accent, bg, fg, label) colours for the avg-score card."""
    if avg_score == 100:
        return '#10B981', '#D1FAE5', '#065F46', '✅ OK'
    if avg_score >= 98:
        return '#F59E0B', '#FEF3C7', '#92400E', '⚠️ Warning'
    return '#EF4444', '#FEE2E2', '#991B1B', '❌ KO'


def _build_checks_summary_html(records: list) -> str:
    """Build the per-check colour-coded summary string."""
    parts = []
    for r in records:
        status = r['dataset_status'].upper()
        color = '#10B981' if status == 'OK' else '#F59E0B' if status == 'WARNING' else '#EF4444'
        parts.append(
            f"<span style='color:{color};'>"
            f"{r['check_type'].capitalize()} {float(r['dataset_score']):.1f}%</span>"
        )
    return " &nbsp;·&nbsp; ".join(parts)


def _render_report_header(project_name: str, latest_ts: str) -> None:
    """Render the top meta bar (project name + last-run timestamp)."""
    st.markdown(f"""
    <div style="background:var(--secondary-background-color); border:1px solid rgba(128,128,128,0.2); border-radius:10px;
                padding:0.9rem 1.1rem; margin-bottom:1.8rem;">
        <div style="font-size:0.72rem; color:#9CA3AF;">
            📂 {project_name} &nbsp;·&nbsp; 📅 Last run: {latest_ts}
        </div>
    </div>
    """, unsafe_allow_html=True)


def _render_avg_score_card(latest_df, total_rows_analysed) -> None:
    """Render the overall quality score + rows-analysed card."""
    avg_score = latest_df['dataset_score'].astype(float).mean()
    avg_accent, avg_bg, avg_fg, avg_label = _compute_avg_score_style(avg_score)
    avg_bar = min(avg_score, 100)
    checks_summary = _build_checks_summary_html(latest_df.to_dict('records'))
    rows_display = f"{total_rows_analysed:,}" if total_rows_analysed is not None else "—"

    st.markdown(f"""
    <div style="
        background:var(--background-color);
        border:1px solid rgba(128,128,128,0.2);
        border-left:4px solid {avg_accent};
        border-radius:10px;
        padding:1rem 1.3rem;
        margin-bottom:1.8rem;
        box-shadow:0 1px 4px rgba(0,0,0,0.06);
        display:flex; align-items:center; justify-content:space-between; gap:2rem;
    ">
        <!-- Left: avg score -->
        <div style="flex:1;">
            <div style="display:flex; align-items:center; gap:0.6rem; margin-bottom:0.3rem;">
                <div style="font-size:0.68rem; font-weight:700; color:#9CA3AF;
                            text-transform:uppercase; letter-spacing:0.08em;">
                    📐 Overall Data Quality Score
                </div>
                <span style="background:{avg_bg}; color:{avg_fg};
                             font-size:0.65rem; font-weight:700;
                             padding:3px 10px; border-radius:20px;
                             white-space:nowrap;">
                    {avg_label}
                </span>
            </div>
            <div style="font-size:2.6rem; font-weight:800; color:{avg_accent}; line-height:1;">
                {avg_score:.1f}<span style="font-size:1rem; color:#9CA3AF;">%</span>
            </div>
            <div style="background:var(--secondary-background-color); border-radius:4px; height:5px; margin-top:0.5rem; width:200px;">
                <div style="background:{avg_accent}; width:{avg_bar}%; height:100%; border-radius:4px;"></div>
            </div>
            <div style="font-size:0.68rem; color:#9CA3AF; margin-top:0.45rem;">
                Average of {len(latest_df)} check{"s" if len(latest_df) > 1 else ""}
                &nbsp;·&nbsp; {checks_summary}
            </div>
        </div>
        <!-- Divider -->
        <div style="width:1px; background:rgba(128,128,128,0.2); align-self:stretch;"></div>
        <!-- Right: total rows -->
        <div style="min-width:130px; text-align:center;">
            <div style="font-size:0.68rem; font-weight:700; color:#9CA3AF;
                        text-transform:uppercase; letter-spacing:0.08em; margin-bottom:0.3rem;">
                🗂️ Rows Analysed
            </div>
            <div style="font-size:2.6rem; font-weight:800; color:var(--text-color); line-height:1;">
                {rows_display}
            </div>
            <div style="font-size:0.68rem; color:#9CA3AF; margin-top:0.45rem;">
                total records scanned
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def _render_report_score_cards(latest_df, faulty_by_check: dict) -> None:
    """Render one score card per check type."""
    rows = latest_df.to_dict('records')
    ncols = min(len(rows), 3)
    cols = st.columns(ncols) if ncols > 0 else []
    for i, row in enumerate(rows):
        with cols[i % ncols]:
            st.markdown(
                _create_score_card(
                    check_type=row['check_type'],
                    score=float(row['dataset_score']),
                    status=row['dataset_status'],
                    faulty_count=faulty_by_check.get(row['check_type'], 0),
                ),
                unsafe_allow_html=True,
            )


def _render_report_footer(api_client, job_id: int, dashboard_url) -> None:
    """Render the download + dashboard footer buttons."""
    import base64 as _b64
    st.markdown("---")
    csv_bytes = api_client.download_faulty_records(job_id)

    _a = (
        "display:flex; align-items:center; justify-content:center;"
        "width:100%; height:38px; border-radius:0.5rem;"
        "border:1px solid rgba(128,128,128,0.4);"
        "color:var(--text-color); text-decoration:none;"
        "font-size:0.875rem; font-weight:400; background:transparent;"
        "box-sizing:border-box;"
    )

    col_dl, col_dash = st.columns([0.5, 0.5])
    with col_dl:
        if csv_bytes:
            csv_b64 = _b64.b64encode(csv_bytes).decode()
            st.markdown(
                f'<a href="data:text/csv;base64,{csv_b64}" download="faulty_records_{job_id}.csv" style="{_a}">⬇️ Faulty Records</a>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<a href="#" style="{_a}opacity:0.45; pointer-events:none; cursor:not-allowed;">⬇️ Faulty Records</a>',
                unsafe_allow_html=True,
            )
            st.caption("Faulty records not available")
    with col_dash:
        if dashboard_url:
            st.markdown(
                f'<a href="{dashboard_url}" target="_blank" rel="noopener noreferrer" style="{_a}">📊 DQ Dashboard</a>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<a href="#" style="{_a}opacity:0.45; pointer-events:none; cursor:not-allowed;">📊 DQ Dashboard</a>',
                unsafe_allow_html=True,
            )


def _render_job_report_content(api_client, project_id: int, job_id: int, job_name: str) -> None:
    """Render all content inside the report modal (extracted for complexity)."""
    project_name = _fetch_project_name(api_client, project_id)
    dashboard_url = _fetch_latest_dashboard_url(api_client, job_id)

    with st.spinner("Loading report data..."):
        result = api_client.get_job_report(job_id)

    if result.get('status') != 'success':
        st.warning(f"⚠️ {result.get('message', 'No report data available yet. Please run the job first.')}")
        table = result.get('table_name') or f"dq_{_normalize_name(project_name)}_{_normalize_name(job_name)}_summary_dataset"
        st.info(f"📋 Looking for table: `{table}`")
        return

    data = result.get('data', [])
    if not data:
        st.warning("⚠️ No report data available yet. Please run the job first.")
        return

    df = pd.DataFrame(data)
    latest_df = (
        df.sort_values('execution_timestamp', ascending=False)
          .groupby('check_type', as_index=False)
          .first()
    )

    latest_ts = str(latest_df['execution_timestamp'].iloc[0]).split('.')[0] if not latest_df.empty else '—'

    _render_report_header(project_name, latest_ts)
    _render_avg_score_card(latest_df, result.get('total_rows_analysed'))
    _render_report_score_cards(latest_df, result.get('faulty_by_check', {}))
    _render_report_footer(api_client, job_id, dashboard_url)


def _show_job_report(job: dict):
    """Show job report in a modern modal dialog."""
    job_id = job.get('id')
    job_name = job.get('job_name', 'Unnamed')
    project_id = st.session_state.get('dq_current_project_id')
    api_client = get_api_client()

    @st.dialog(f"📊 Results - {job_name}", width="large")
    def show_report_modal():
        _render_job_report_content(api_client, project_id, job_id, job_name)

    show_report_modal()


def _duplicate_job(job_id: int, project_id: int):
    """Duplicate an existing job"""
    api_client = get_api_client()
    
    with st.spinner("Duplicating job..."):
        # Get job details
        logger.info(f"[JOBS UI] 📋 Duplicating job_id={job_id}")
        result = api_client.get_job_details(job_id)
        logger.info(f"[JOBS UI] Get job for duplication response: status={result.get('status')}")
        if result.get('status') != 'success':
            logger.error(f"[JOBS UI] ❌ Failed to duplicate: {result.get('message')}")
            st.error(f"❌ Failed to duplicate: {result.get('message')}")
            return
        
        job = result.get('job', {})
        user_email = st.session_state.get('current_user', _UNKNOWN_USER_EMAIL)
        
        # Create new job with same config
        new_job_data = {
            'job_name': f"{job.get('job_name', 'Job')} (Copy)",
            'job_description': job.get('job_description', ''),
            'status': 'draft',
            'step': 1,
            'source_config': job.get('source_config', {}),
            'quality_config': job.get('quality_config', {}),
            'deployed_by': user_email
        }
        
        logger.info(f"[JOBS UI] Creating duplicate job with data: {new_job_data}")
        create_result = api_client.create_project_job(project_id, new_job_data)
        logger.info(f"[JOBS UI] ✅ Duplicate job creation response: status={create_result.get('status')}, job_id={create_result.get('job_id')}")
        
        if create_result.get('status') == 'success':
            st.toast("Job duplicated successfully!", icon="✅")
            st.rerun()
        else:
            logger.error(f"[JOBS UI] ❌ Failed to duplicate: {create_result.get('message')}")
            st.error(f"❌ Failed to duplicate: {create_result.get('message')}")


def _parse_json_field(value) -> dict:
    """Parse a field that may be a JSON string or already a dict."""
    import json
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return {}
    return value or {}


def _restore_csv_preview_from_url(source_config: dict, nested_config: dict) -> None:
    """Restore dataset preview state for CSV source type."""
    import pandas as pd
    try:
        columns = (nested_config.get('columns') if nested_config else None) or source_config.get('columns', [])
        if columns:
            st.session_state['dq_dataset_preview'] = pd.DataFrame(columns=columns)
            st.session_state['dq_df_columns_cache'] = columns
            ds_name = (nested_config or {}).get('file_name') or source_config.get('file_name') or source_config.get('dataset_name', 'Dataset')
            st.session_state['dq_dataset_name'] = ds_name
            logger.info(f"[JOBS UI] ✅ Restored preview from URL with {len(columns)} columns")
        else:
            st.session_state['dq_dataset_preview'] = pd.DataFrame()
            logger.warning("[JOBS UI] ⚠️ No columns found for CSV restore from URL")
    except Exception as e:
        logger.error(f"[JOBS UI] ❌ Failed to restore preview from URL: {e}")


def _restore_uc_preview_from_url(source_config: dict, nested_config: dict) -> None:
    """Restore dataset preview state for Unity Catalog source type."""
    import pandas as pd
    uc_columns = nested_config.get('columns') or source_config.get('columns', [])
    if uc_columns:
        st.session_state['dq_dataset_preview'] = pd.DataFrame(columns=uc_columns)
        st.session_state['dq_df_columns_cache'] = uc_columns
    else:
        st.session_state['dq_dataset_preview'] = pd.DataFrame()
    st.session_state['dq_unity_catalog'] = source_config.get('catalog')
    st.session_state['dq_unity_schema'] = source_config.get('schema')
    st.session_state['dq_unity_table'] = source_config.get('table')
    st.session_state['dq_dataset_name'] = f"{source_config.get('catalog')}.{source_config.get('schema')}.{source_config.get('table')}"
    logger.info(f"[JOBS UI] ✅ Marked Unity Catalog dataset as loaded from URL with {len(uc_columns)} columns")


def _restore_source_config_from_url(source_config: dict) -> None:
    """Write source config fields to session state."""
    if not source_config:
        return
    logger.info(f"[JOBS UI] 📋 Restoring source config from URL: {list(source_config.keys())}")
    st.session_state['dq_source_type'] = source_config.get('source_type')
    st.session_state['dq_catalog'] = source_config.get('catalog')
    st.session_state['dq_schema'] = source_config.get('schema')
    st.session_state['dq_table'] = source_config.get('table')
    st.session_state['dq_dbfs_path'] = source_config.get('volume_path')
    st.session_state['dq_file_name'] = source_config.get('file_name')
    st.session_state['dq_dataset_name'] = source_config.get('dataset_name')
    nested_config = source_config.get('source_config', {})
    st.session_state['dq_source_config'] = nested_config
    source_type = source_config.get('source_type')
    if source_type == 'csv':
        _restore_csv_preview_from_url(source_config, nested_config)
    elif source_type == 'unity_catalog':
        _restore_uc_preview_from_url(source_config, nested_config)


def _restore_quality_config_from_url(quality_config: dict) -> None:
    """Write quality config fields to session state."""
    if not quality_config:
        return
    logger.info(f"[JOBS UI] 🎯 Restoring quality config from URL: {list(quality_config.keys())}")
    st.session_state['dq_selected_components'] = quality_config.get('selected_components', [])
    st.session_state['dq_component_configs'] = quality_config.get('component_configs', {})
    st.session_state['dq_component_enabled'] = quality_config.get('component_enabled', {})
    st.session_state['dq_thresholds'] = quality_config.get('thresholds', {})
    logger.info(f"[JOBS UI] ✅ Restored {len(st.session_state.get('dq_selected_components', []))} components from URL")


def _restore_deployment_config_from_url(deployment_config: dict, job: dict, job_id: int) -> None:
    """Write deployment config fields to session state, reconstructing if needed."""
    if not deployment_config and job.get('databricks_job_id'):
        logger.info("[JOBS UI] 🔧 Reconstructing deployment info from dedicated columns (URL load)")
        deployment_config = {
            'databricks_job_id': job.get('databricks_job_id'),
            'job_url': job.get('databricks_job_url', ''),
            'workspace_path': job.get('workspace_path', ''),
            'db_job_id': job_id,
            'status': job.get('status'),
        }
    if deployment_config and deployment_config.get('databricks_job_id'):
        logger.info("[JOBS UI] 🚀 Restoring deployment config from URL")
        st.session_state['dq_deployment_result'] = deployment_config
        st.session_state['dq_deployed_job_id'] = (
            deployment_config.get('db_job_id')
            or deployment_config.get('databricks_job_id')
            or deployment_config.get('job_id')
        )
        logger.info(f"[JOBS UI] ✅ Restored deployment info from URL: databricks_job_id={st.session_state.get('dq_deployed_job_id')}")
    else:
        logger.info("[JOBS UI] 📝 No deployment config from URL - job not deployed yet")


def load_job_config_from_url(job_id: int, project_id: int):
    """
    Load job configuration when page is restored from URL parameters.
    This is similar to _load_job_into_workflow but doesn't change view mode
    since we're already restoring it from URL.
    """
    api_client = get_api_client()

    logger.info(f"[JOBS UI] 🔄 Loading job config from URL - job_id={job_id}, project_id={project_id}")
    result = api_client.get_job_details(job_id)

    if result.get('status') != 'success':
        logger.error(f"[JOBS UI] ❌ Failed to load job from URL: {result.get('message')}")
        return

    # Backend returns 'data' not 'job'
    job = result.get('data', result.get('job', {}))

    logger.info(f"[JOBS UI] 📦 Job data received from URL: step={job.get('step')}, name={job.get('job_name')}")
    logger.info(f"[JOBS UI] 📦 source_config present: {bool(job.get('source_config'))}, type: {type(job.get('source_config'))}")

    # Set workflow context (already set from URL params, but ensure consistency)
    st.session_state['dq_in_project_mode'] = True
    st.session_state['dq_job_name'] = job.get('job_name', '')
    st.session_state['dq_job_description'] = job.get('job_description', '')

    _restore_source_config_from_url(_parse_json_field(job.get('source_config', {})))
    _restore_quality_config_from_url(_parse_json_field(job.get('quality_config', {})))
    _restore_deployment_config_from_url(_parse_json_field(job.get('deployment_config', {})), job, job_id)

    # Restore run count from database
    run_count = job.get('run_count', 0)
    if run_count:
        st.session_state['dq_run_count'] = run_count
        logger.info(f"[JOBS UI] 🎯 Restored run count from URL: {run_count}")

    logger.info("[JOBS UI] ✅ Job config fully restored from URL")
