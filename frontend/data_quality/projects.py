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
Data Quality Projects Management Page

This page allows users to:
- Create new data quality projects
- View and manage existing projects
- Edit project configurations
- Delete projects
- Access project details
- View last run reports with quality metrics
"""

import streamlit as st
import json
import pandas as pd
from datetime import datetime
import time
import sys
import os

def _get_project_share_count(project):
    """
    Returns the number of users this project is shared with (emails).
    Expects project['shared_with'] to be a list of emails.
    """
    shared_with = project.get('shared_with', [])
    return len(shared_with)

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api_client import get_api_client
from data_quality.components import show_report_dialog
from utils.async_loader import AsyncDataLoader
from utils.loading_ui import show_loading_indicator


def _validate_new_project_name(project_name: str) -> bool:
    """Check name is non-empty and unique; show error and return False if not."""
    if not project_name or not project_name.strip():
        st.error("⚠️ Project name is required!")
        return False
    existing_names = [p['name'] for p in st.session_state.dq_projects]
    if project_name.strip() in existing_names:
        st.error("❌ A project with this name already exists. Please choose a different name.")
        return False
    return True


def _execute_create_project(api_client, project_name: str, project_description: str) -> None:
    """Call the API to create a project and apply an optimistic local update."""
    user_email = st.session_state.get('current_user', 'unknown@example.com')
    description = project_description.strip() if project_description else ""
    try:
        result = api_client.create_project(
            user_email=user_email,
            project_name=project_name.strip(),
            description=description,
        )
    except Exception as e:
        st.error(f"❌ Error creating project: {str(e)}")
        return

    if result.get('status') != 'success':
        st.error(f"❌ Failed to create project: {result.get('message', 'Unknown error')}")
        return

    project_id = result.get('project_id')
    new_project = {
        'id': project_id,
        'name': project_name.strip(),
        'description': description,
        'status': 'draft',
        'created_at': datetime.now().isoformat(),
        'last_modified': datetime.now().isoformat(),
        'step': 1,
        'config': {},
        'job_stats': {'total': 0, 'deployed': 0, 'configured': 0, 'draft': 0},
    }
    st.session_state.dq_projects.append(new_project)
    if 'dq_projects_dict' not in st.session_state:
        st.session_state.dq_projects_dict = {}
    st.session_state.dq_projects_dict[project_id] = new_project
    AsyncDataLoader.invalidate_cache("dq_projects")
    st.session_state['show_create_project_modal'] = False
    st.rerun()


def _show_create_project_modal(api_client):
    """Show modal dialog to create a new project."""
    @st.dialog("🆕 Create New Project", width="large")
    def create_project_dialog():
        st.markdown("#### Define Your New Project")
        st.markdown("Enter a name and description to identify this data quality project.")
        st.markdown("")

        project_name = st.text_input(
            "Project Name *",
            placeholder="e.g., Customer Data Quality Check",
            key="new_project_name_input",
        )
        project_description = st.text_area(
            "Description (optional)",
            placeholder="Brief description of what this project checks...",
            key="new_project_description_input",
            height=120,
        )

        st.markdown("---")
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("❌ Cancel", width="stretch"):
                st.session_state['show_create_project_modal'] = False
                st.rerun()
        with col2:
            if st.button("✅ Create Project", width="stretch", type="primary", disabled=not project_name):
                if _validate_new_project_name(project_name):
                    _execute_create_project(api_client, project_name, project_description)

    create_project_dialog()


def _initialize_page_timing() -> None:
    """Reset page-load timing when the user first arrives on this page."""
    if 'dq_page_load_start' not in st.session_state or st.session_state.get('dq_page_changed', False):
        st.session_state.dq_page_load_start = time.time()
        st.session_state.dq_load_time_displayed = False
        st.session_state.dq_page_changed = False


def _load_projects(api_client, user_email: str) -> bool:
    """Load projects via AsyncDataLoader (cache or API). Returns False on failure."""
    import logging
    force_refresh = st.session_state.get('dq_projects_refresh', False)
    logging.info(f"[Projects] Loading projects (force_refresh={force_refresh})")

    cache_available = AsyncDataLoader.has_valid_cache("dq_projects", ttl_seconds=300)
    logging.info(f"[Projects] Cache available: {cache_available}")

    loader_kwargs = dict(
        cache_key="dq_projects",
        loader_func=lambda: api_client.get_projects(user_email),
        ttl_seconds=300,
        force_refresh=force_refresh,
    )
    # Show spinner only when a real API call is needed
    if not cache_available or force_refresh:
        with st.spinner("Loading projects from API..."):
            cached_projects = AsyncDataLoader.load_in_background(**loader_kwargs)
    else:
        cached_projects = AsyncDataLoader.load_in_background(**loader_kwargs)

    if cached_projects is None:
        st.error("Failed to load projects. Please refresh the page.")
        return False

    st.session_state.dq_projects = cached_projects
    st.session_state.dq_projects_dict = {p['id']: p for p in cached_projects}
    st.session_state.dq_projects_loaded = True
    st.session_state.dq_load_time = (time.time() - st.session_state.dq_page_load_start) * 1000
    st.session_state.dq_cache_was_used = cache_available

    if force_refresh:
        st.session_state.dq_projects_refresh = False
    return True


def _filter_projects(projects: list, search_term: str, filter_status: str) -> list:
    """Return *projects* filtered by search term and status selectbox value."""
    result = projects
    if search_term:
        q = search_term.lower()
        result = [p for p in result
                  if q in p['name'].lower() or q in p.get('description', '').lower()]
    if filter_status != "All":
        status_map = {"Draft": "draft", "Configured": "configured", "Deployed": "deployed"}
        target = status_map.get(filter_status, filter_status.lower())
        result = [p for p in result if p['status'] == target]
    return result


def _render_projects_list(filtered_projects: list) -> None:
    """Render project cards and open the share modal for the requesting project."""
    if not filtered_projects:
        st.info("🔍 No projects found matching your criteria.")
        return

    share_modal_project_id = None
    for project in filtered_projects:
        _render_project_card(project)
        if st.session_state.get(f"show_share_modal_{project['id']}", False):
            share_modal_project_id = project['id']

    if share_modal_project_id is None:
        return
    project = next((p for p in filtered_projects if p['id'] == share_modal_project_id), None)
    if project:
        _show_share_modal(project)


def _render_shared_with_me_section(api_client, user_email: str) -> None:
    """Render the 'Projects shared with me' section at the bottom of the page."""
    st.markdown("---")
    if not user_email:
        return
    user_info = api_client.get_user(user_email)
    user_id = user_info.get('user', {}).get('id')
    shared_projects = []
    if user_id:
        shared_projects = api_client.get_projects_shared_with_user(user_id).get('projects', [])

    if shared_projects:
        st.markdown("#### Projects shared with me")
        for project in shared_projects:
            _render_project_card(project)
    else:
        st.info("No projects have been shared with you yet.")


def render_projects_management():
    """Render the projects management page."""
    _initialize_page_timing()

    api_client = get_api_client()
    user_email = st.session_state.get('current_user', 'unknown@example.com')

    if 'dq_projects' not in st.session_state:
        st.session_state.dq_projects = []

    if not _load_projects(api_client, user_email):
        return

    # Page header
    st.markdown("## 📂 Projects Management")
    st.markdown("Create, manage, and monitor your data quality projects")
    st.markdown("")

    with st.expander("ℹ️ How it works"):
        st.markdown("""
        ### Getting Started with Data Quality Projects

        Follow these simple steps to set up and run your data quality checks:

        1. **Create a new project** - Start by creating a DQ project to organize your quality checks
        2. **Choose a data source** - Select your data from Unity Catalog or upload a CSV file
        3. **Choose controls** - Configure quality checks like completeness, uniqueness, and validity
        4. **Deploy DQ job** - Deploy your configuration as a Databricks job
        5. **Run DQ job** - Execute the job and monitor quality metrics

        Each project can contain multiple jobs with different configurations.
        """)

    st.markdown("---")

    # Search, filter, and new project button on same row
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        search_term = st.text_input("🔍 Search projects", placeholder="Search by name or description...")
    with col2:
        filter_status = st.selectbox("Filter by status", ["All", "Draft", "Configured", "Deployed"])
    with col3:
        st.markdown("""
            <style>
            div[data-testid="column"]:nth-child(3) .stButton button {
                height: 38px;
                margin-top: 11px;
            }
            </style>
        """, unsafe_allow_html=True)
        if st.button("➕ New Project", type="primary", width="stretch"):
            st.session_state['show_create_project_modal'] = True
            st.rerun()

    if st.session_state.get('show_create_project_modal', False):
        _show_create_project_modal(api_client)

    if st.session_state.dq_projects:
        st.markdown("---")
        st.markdown("#### Projects")
        filtered = _filter_projects(st.session_state.dq_projects, search_term, filter_status)
        _render_projects_list(filtered)
    else:
        st.info("💡 No projects yet. Click on the button above and create your first DQ project!")

    _render_shared_with_me_section(api_client, user_email)


def _render_project_card(project):
    """Render a single project card"""
    # Status badge colors
    status_colors = {
        'deployed': '#10B981',
        'configured': '#3B82F6',
        'draft': '#F59E0B'
    }
    status_icons = {
        'deployed': '✅',
        'configured': '⚙️',
        'draft': '📝'
    }
    
    status = project['status']
    status_color = status_colors.get(status, '#F59E0B')
    status_icon = status_icons.get(status, '📝')
    
    # Get job statistics
    job_stats = project.get('job_stats', {'total': 0, 'deployed': 0, 'configured': 0, 'draft': 0})
    
    with st.container():
        # Compact card with less padding
        st.markdown(f"""
            <div style="
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                padding: 12px 15px;
                margin-bottom: 10px;
                background-color: #FFFFFF;
            ">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 8px;">
                    <div style="flex: 1;">
                        <h4 style="margin: 0; color: #1F2937; font-size: 1.1rem;">📊 {project['name']}</h4>
                        <p style="margin: 3px 0 5px 0; color: #6B7280; font-size: 0.85rem;">{project.get('description', 'No description')[:80]}{'...' if len(project.get('description', '')) > 80 else ''}</p>
                        <div style="color: #9CA3AF; font-size: 0.75rem; margin-top: 5px;">
                            <span>📅 {datetime.fromisoformat(project['created_at']).strftime('%Y-%m-%d')}</span>
                        </div>
                    </div>
                    <div style="
                        background-color: {status_color}15;
                        color: {status_color};
                        padding: 4px 12px;
                        border-radius: 12px;
                        font-size: 0.75rem;
                        font-weight: 600;
                        white-space: nowrap;
                        margin-left: 15px;
                    ">
                        {status_icon} {status.capitalize()}
                    </div>
                </div>
                <div style="display: flex; gap: 12px; color: #6B7280; font-size: 0.8rem; margin-bottom: 10px;">
                    <span>📊 {job_stats['total']} Jobs</span>
                    <span>✅ {job_stats['deployed']} Deployed</span>
                    <span>⚙️ {job_stats['configured']} Configured</span>
                    <span>📝 {job_stats['draft']} Draft</span>
                    <span>🤝 { _get_project_share_count(project) } Shared</span>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        # Compact action buttons with hamburger menu
        col1, col2 = st.columns([5, 1])
        
        with col1:
            if st.button("Open", key=f"jobs_{project['id']}", width="stretch", type="primary"):
                _navigate_to_jobs(project['id'])
        

        with col2:
            # Hamburger menu for actions using st.popover for instant menu (vertical layout)
            with st.popover("⋮", width="stretch"):
                if st.button("Edit", key=f"edit_{project['id']}", width="stretch"):
                    _show_project_edit_dialog(project)
                if st.button("Details", key=f"details_{project['id']}", width="stretch"):
                    _show_project_details(project)
                if st.button("Share", key=f"share_{project['id']}", width="stretch"):
                    st.session_state[f"show_share_modal_{project['id']}"] = True
                # Le bouton Unshare est supprimé, la gestion se fait dans le modal Share
                if st.button("Delete", key=f"delete_{project['id']}", width="stretch", type="secondary"):
                    st.session_state[f"confirm_delete_{project['id']}"] = True

        # Ouvre le dialog de confirmation hors du popover (même pattern que le share modal)
        if st.session_state.get(f"confirm_delete_{project['id']}", False):
            _show_delete_confirmation_dialog(project)


# --- Share modal helpers -------------------------------------------------------

def _resolve_owner_user_id(api_client, owner_email: str) -> str | None:
    """Fetch the owner's backend user ID; show error and return None on failure."""
    user_info = api_client.get_user(owner_email)
    owner_user_id = user_info.get('user', {}).get('id')
    if not owner_user_id:
        st.error("Owner user ID not found in backend.")
    return owner_user_id


def _execute_unshare(api_client, project: dict, owner_user_id: str, email: str) -> None:
    """Call the API to remove *email*'s access and update the local project cache."""
    result = api_client.unshare_project(project['id'], owner_user_id, email)
    if result.get("status") == "success":
        st.toast(f"Unshared with {email}", icon="✅")
        project['shared_with'] = [e for e in project['shared_with'] if e != email]
    else:
        st.toast(f"Failed to unshare with {email}: {result.get('message', 'Unknown error')}", icon="❌")
    st.session_state[f"confirm_unshare_{project['id']}_{email}"] = False
    st.rerun()


def _render_unshare_confirm_row(api_client, project: dict, owner_email: str, email: str) -> None:
    """Render one shared-user row and its inline unshare confirmation."""
    col1, col2 = st.columns([6, 1])
    with col1:
        st.markdown(f"**{email}**")
    with col2:
        if st.button("❌", key=f"unshare_cross_{project['id']}_{email}", width="stretch"):
            st.session_state[f"confirm_unshare_{project['id']}_{email}"] = True

    if not st.session_state.get(f"confirm_unshare_{project['id']}_{email}", False):
        return

    st.warning(f"Remove access for {email}?")
    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("Cancel", key=f"cancel_unshare_cross_{project['id']}_{email}", width="stretch"):
            st.session_state[f"confirm_unshare_{project['id']}_{email}"] = False
            st.rerun()
    with c2:
        if st.button("Yes, Remove", key=f"confirm_unshare_cross_{project['id']}_{email}", width="stretch", type="primary"):
            owner_user_id = _resolve_owner_user_id(api_client, owner_email)
            if owner_user_id:
                _execute_unshare(api_client, project, owner_user_id, email)


def _render_shared_users_list(api_client, project: dict, owner_email: str) -> None:
    """Section 1: list current shared users with inline unshare option per row."""
    st.markdown("#### Shared with")
    shared_with_display = [e for e in project.get('shared_with', []) if e != owner_email]
    if not shared_with_display:
        st.info("No users have access yet.")
        return
    for email in shared_with_display:
        _render_unshare_confirm_row(api_client, project, owner_email, email)


def _execute_share_batch(api_client, project: dict, owner_user_id: str, selected_emails: list) -> None:
    """Share the project with multiple users; report success or per-user errors."""
    errors = []
    for email in selected_emails:
        result = api_client.share_project(project['id'], owner_user_id, email)
        if result.get("status") != "success":
            errors.append(f"{email}: {result.get('message', 'Unknown error')}")
        else:
            project['shared_with'].append(email)
    if not errors:
        st.toast("Project shared successfully!", icon="✅")
        st.session_state[f"show_share_modal_{project['id']}"] = False
        st.rerun()
    else:
        st.toast("Some shares failed:\n" + "\n".join(errors), icon="❌")


def _render_add_users_section(api_client, project: dict, owner_email: str) -> None:
    """Section 2: multiselect for new users + Share / Cancel buttons."""
    st.markdown("#### Add users to share with")
    shared_with = project.get('shared_with', [])
    users = api_client.get_all_users()
    user_options = [u for u in users if u['email'] != owner_email and u['email'] not in shared_with]
    user_labels = [f"{u['username'] or u['email']} ({u['email']})" for u in user_options]
    email_to_user = {label: u['email'] for u, label in zip(user_options, user_labels)}
    selected_labels = st.multiselect("Select users to share with", options=user_labels, key=f"share_multiselect_{project['id']}")
    selected_emails = [email_to_user[label] for label in selected_labels]

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Cancel", width="stretch"):
            st.session_state[f"show_share_modal_{project['id']}"] = False
            st.rerun()
    with col2:
        if st.button("Share", width="stretch", type="primary"):
            if not selected_emails:
                st.error("Please select at least one user.")
                return
            owner_user_id = _resolve_owner_user_id(api_client, owner_email)
            if owner_user_id:
                _execute_share_batch(api_client, project, owner_user_id, selected_emails)


# --- Centralisation du modal Share pour éviter l'erreur Streamlit ---
def _show_share_modal(project):
    """Show the share project dialog (orchestrator — delegates to focused helpers)."""
    @st.dialog(f"Share Project: {project['name']}")
    def share_project_dialog():
        api_client = get_api_client()
        owner_email = st.session_state.get('current_user')
        _render_shared_users_list(api_client, project, owner_email)
        st.markdown("---")
        _render_add_users_section(api_client, project, owner_email)
    share_project_dialog()


def _show_delete_confirmation_dialog(project):
    """Show delete confirmation dialog for a project."""
    @st.dialog(f"Delete Project: {project['name']}")
    def confirm_delete_dialog():
        st.warning(f"⚠️ Are you sure you want to delete '{project['name']}'? This action cannot be undone.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Yes, Delete", key=f"confirm_yes_{project['id']}", width="stretch", type="primary"):
                _delete_project(project['id'])
                st.session_state[f"confirm_delete_{project['id']}"] = False
        with col2:
            if st.button("Cancel", key=f"confirm_cancel_{project['id']}", width="stretch"):
                st.session_state[f"confirm_delete_{project['id']}"] = False
                st.rerun()
    confirm_delete_dialog()


def _navigate_to_jobs(project_id):
    """Navigate to jobs management for a project"""
    st.session_state['dq_view_mode'] = 'jobs'
    st.session_state['dq_current_project_id'] = project_id
    # Update URL parameters
    st.query_params.update({'view_mode': 'jobs', 'project_id': str(project_id)})
    st.rerun()


def _parse_project_config(project: dict) -> tuple[dict, int]:
    """Extract and normalise the config dict and current step from a project record."""
    config = project.get('config', {})
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except Exception as e:
            st.error(f"⚠️ Error loading project configuration: {str(e)}")
            config = {}
    step = project.get('step') or config.get('step') or 1
    return config, int(step)


def _restore_session_from_config(project_id: str, config: dict, step: int) -> None:
    """Write all workflow session-state keys from a loaded project config."""
    st.session_state.dq_current_project_id = project_id
    st.session_state.current_project_id = project_id   # backward compatibility
    st.session_state.dq_in_project_mode = True
    st.session_state.dq_step = step
    st.session_state.dq_max_step_reached = step
    print(f"[LoadProject] Loaded project {project_id} at step {step}")
    # Data source
    st.session_state.dq_source_type = config.get('source_type')
    st.session_state.dq_dataset_name = config.get('dataset_name')
    st.session_state.dq_source_config = config.get('source_config', {})
    st.session_state.dq_dbfs_path = config.get('volume_path')
    # Quality controls
    st.session_state.dq_selected_components = config.get('selected_components', [])
    st.session_state.dq_component_configs = config.get('component_configs', {})
    st.session_state.dq_thresholds = config.get('thresholds', {})
    st.session_state.dq_component_enabled = config.get('component_enabled', {})
    # Job
    st.session_state.dq_job_name = config.get('job_name')
    st.session_state.dq_job_description = config.get('job_description')
    # Deployment
    st.session_state.dq_deployed_job_id = config.get('deployed_job_id')
    st.session_state.dq_deployment_result = config.get('deployment_result')


def _apply_csv_cache_hit(cached_data: dict, dbfs_path: str, config: dict) -> None:
    """Restore CSV preview and flags from an in-memory cache entry."""
    st.session_state.dq_dataset_preview = cached_data['df']
    st.session_state.dq_dataset_name = cached_data.get('dataset_name', config.get('dataset_name'))
    st.session_state.dq_dbfs_path = cached_data.get('volume_path', dbfs_path)
    st.session_state.dq_source_config = cached_data.get('config', config.get('source_config', {}))
    st.session_state.csv_uploaded_to_dbfs = True
    st.session_state.existing_csv_loaded = True
    st.session_state.selected_csv_path = dbfs_path
    st.session_state.selected_csv_name = config.get('source_config', {}).get('file_name', 'file.csv')
    st.session_state.dq_df_columns_cache = cached_data['df'].columns.tolist()


def _apply_csv_fetch_result(result: dict, dbfs_path: str, config: dict, cache_key: str, step: int) -> None:
    """Store a freshly fetched CSV preview into session state and cache."""
    preview_data = result.get('preview', [])
    if preview_data:
        df = pd.DataFrame(preview_data)
        st.session_state.dq_dataset_preview = df
        st.session_state[cache_key] = {
            'df': df,
            'dataset_name': config.get('dataset_name'),
            'volume_path': dbfs_path,
            'config': config.get('source_config', {}),
        }
        st.session_state.dq_df_columns_cache = df.columns.tolist()
    st.session_state.csv_uploaded_to_dbfs = True
    st.session_state.existing_csv_loaded = True
    st.session_state.selected_csv_path = dbfs_path
    st.session_state.selected_csv_name = config.get('source_config', {}).get('file_name', 'file.csv')
    st.toast(f"Loaded project from Step {step} with CSV data", icon="✅")


def _restore_csv_preview_on_load(api_client, project_id: str, config: dict, step: int) -> None:
    """Restore CSV dataset preview — cache hit is instant, cache miss fetches from DBFS."""
    dbfs_path = config.get('volume_path')
    if not dbfs_path:
        return
    cache_key = f'csv_preview_{dbfs_path}'
    if cache_key in st.session_state:
        _apply_csv_cache_hit(st.session_state[cache_key], dbfs_path, config)
        return
    try:
        result = api_client.preview_csv_from_dbfs(project_id=project_id, file_path=dbfs_path)
        if result.get('status') == 'success':
            _apply_csv_fetch_result(result, dbfs_path, config, cache_key, step)
    except Exception as e:
        st.error(f"⚠️ Could not reload CSV preview: {str(e)}")
        if step > 1:
            st.session_state.dq_dataset_preview = pd.DataFrame()
            st.warning("📝 CSV file info restored from config but preview unavailable. You can still proceed.")


def _handle_uc_preview_error(preview_data: dict, catalog: str, schema: str, table: str) -> None:
    """Show the appropriate error message for a failed Unity Catalog preview."""
    if preview_data.get('permission_error'):
        st.error("⛔ **Insufficient Permissions on Saved Table**")
        st.warning(
            f"You no longer have **SELECT** privilege on table `{catalog}.{schema}.{table}`.\n\n"
            "This project was saved with a table you cannot access.\n\n"
            "**Action:** Contact your administrator to restore your SELECT privileges, or select a different table."
        )
    else:
        st.error(f"⚠️ Could not reload Unity Catalog preview: {preview_data.get('message', 'Unknown error')}")
    st.session_state.dq_dataset_preview = pd.DataFrame()


def _restore_uc_preview_on_load(api_client, config: dict, step: int) -> None:
    """Restore Unity Catalog dataset preview from the saved catalog/schema/table."""
    source_config = config.get('source_config', {})
    catalog = source_config.get('catalog')
    schema = source_config.get('schema')
    table = source_config.get('table')
    if not (catalog and schema and table):
        return
    try:
        preview_data = api_client.preview_table(catalog, schema, table)
        if preview_data.get('status') == 'error':
            _handle_uc_preview_error(preview_data, catalog, schema, table)
            return
        preview = preview_data.get('preview')
        if not preview:
            return
        df = (pd.DataFrame(preview['sample_data']) if preview.get('sample_data')
              else pd.DataFrame(columns=preview.get('columns', [])))
        st.session_state.dq_dataset_preview = df
        st.session_state.dq_df_columns_cache = df.columns.tolist()
        st.session_state.dq_unity_catalog = catalog
        st.session_state.dq_unity_schema = schema
        st.session_state.dq_unity_table = table
        st.toast(f"Loaded project from Step {step} with Unity Catalog data", icon="✅")
    except Exception as e:
        st.error(f"⚠️ Could not reload Unity Catalog preview: {str(e)}")
        if step > 1:
            st.session_state.dq_dataset_preview = pd.DataFrame()
            st.warning("📝 Unity Catalog connection restored from config but preview unavailable.")


def _restore_dataset_preview(api_client, project_id: str, config: dict, step: int) -> None:
    """Dispatch to the correct preview-restore helper based on source type."""
    source_type = config.get('source_type')
    if source_type == 'csv' and config.get('volume_path'):
        _restore_csv_preview_on_load(api_client, project_id, config, step)
    elif source_type == 'unity_catalog':
        _restore_uc_preview_on_load(api_client, config, step)


def _load_project(project_id):
    """Load a project and enter edit mode — restores full session state from database."""
    api_client = get_api_client()
    project_result = api_client.get_project(project_id)

    if project_result.get('status') != 'success':
        st.error(f"⚠️ Failed to load project: {project_result.get('message', 'Unknown error')}")
        return

    project = project_result['project']
    config, step = _parse_project_config(project)
    _restore_session_from_config(project_id, config, step)
    _restore_dataset_preview(api_client, project_id, config, step)


def _show_project_details(project):
    """Show project details in a modal dialog"""
    @st.dialog(f"📋 Project Details: {project['name']}")
    def show_details():
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Project Information**")
            st.markdown(f"- **ID**: `{project['id']}`")
            st.markdown(f"- **Name**: {project['name']}")
            st.markdown(f"- **Status**: {project['status'].capitalize()}")
            st.markdown(f"- **Current Step**: Step {project.get('step', 1)}")
            shared_with = project.get('shared_with', [])
            st.markdown(f"- **Shared with**: {len(shared_with)} user(s)")
            if shared_with:
                st.markdown("  - " + "\n  - ".join(shared_with))
        
        with col2:
            st.markdown("**Timestamps**")
            st.markdown(f"- **Created**: {datetime.fromisoformat(project['created_at']).strftime('%Y-%m-%d %H:%M:%S')}")
            st.markdown(f"- **Modified**: {datetime.fromisoformat(project['last_modified']).strftime('%Y-%m-%d %H:%M:%S')}")
        
        st.markdown("---")
        st.markdown("**Description**")
        st.markdown(project.get('description', 'No description provided'))
        
        st.markdown("---")
        st.markdown("**Configuration**")
        config = project.get('config', {})
        if config:
            st.json(config)
        else:
            st.info("No configuration yet. Click 'Configure' to set up this project.")
        
        st.markdown("---")
        if st.button("Close", width="stretch", type="primary"):
            st.rerun()
    
    show_details()


def _apply_project_edit(project_id: str, new_name: str, new_description: str) -> None:
    """Persist a name/description edit and refresh the local project cache."""
    api_client = get_api_client()
    result = api_client.update_project(project_id, {'name': new_name, 'description': new_description})
    if result.get('status') != 'success':
        st.error(f"❌ Failed to update: {result.get('message')}")
        return
    st.toast("Project updated successfully!", icon="✅")
    for p in st.session_state.dq_projects:
        if p['id'] == project_id:
            p['name'] = new_name
            p['description'] = new_description
            p['last_modified'] = datetime.now().isoformat()
    st.session_state.dq_projects_dict[project_id]['name'] = new_name
    st.session_state.dq_projects_dict[project_id]['description'] = new_description
    st.rerun()


def _show_project_edit_dialog(project):
    """Show project edit dialog for name and description."""
    @st.dialog(f"✏️ Edit Project: {project['name']}")
    def show_edit():
        new_name = st.text_input("Project Name", value=project['name'])
        new_description = st.text_area("Description", value=project.get('description', ''), height=100)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 Save Changes", width="stretch", type="primary"):
                if not new_name:
                    st.error("❌ Project name cannot be empty")
                else:
                    _apply_project_edit(project['id'], new_name, new_description)
        with col2:
            if st.button("Cancel", width="stretch"):
                st.rerun()

    show_edit()


def _duplicate_project(project):
    """Duplicate an existing project"""
    api_client = get_api_client()
    
    # Get current user email
    user_email = st.session_state.get('current_user', 'unknown@geodis.com')
    
    # Call backend to duplicate the project
    result = api_client.duplicate_project(project['id'], user_email)
    
    if result.get('status') == 'success':
        # Add duplicated project to cache instead of full refresh
        new_project_id = result.get('project_id')
        duplicated_project = {
            'id': new_project_id,
            'name': f"{project['name']} (Copy)",
            'description': project.get('description', ''),
            'status': 'draft',
            'created_at': datetime.now().isoformat(),
            'last_modified': datetime.now().isoformat(),
            'step': project.get('step', 1),
            'config': project.get('config', {})
        }
        st.session_state.dq_projects.append(duplicated_project)
        st.session_state.dq_projects_dict[new_project_id] = duplicated_project
        st.toast("Project duplicated successfully!", icon="✅")
        st.rerun()
    else:
        st.error(f"❌ Failed to duplicate project: {result.get('message', 'Unknown error')}")


def _delete_project(project_id):
    """Delete a project"""
    api_client = get_api_client()
    result = api_client.delete_project(project_id)
    
    if result.get('status') == 'success':
        # Remove from local cache instead of full refresh
        st.session_state.dq_projects = [p for p in st.session_state.dq_projects if p['id'] != project_id]
        if project_id in st.session_state.dq_projects_dict:
            del st.session_state.dq_projects_dict[project_id]
        # Invalidate cache to force refresh on next load
        AsyncDataLoader.invalidate_cache("dq_projects")
        st.toast("Project deleted successfully!", icon="✅")
        st.rerun()
    else:
        st.error(f"❌ Failed to delete project: {result.get('message', 'Unknown error')}")


def _build_project_config() -> dict:
    """Collect all workflow session-state keys into a single config dict."""
    return {
        # Data source configuration
        'source_type': st.session_state.get('dq_source_type'),
        'dataset_name': st.session_state.get('dq_dataset_name'),
        'source_config': st.session_state.get('dq_source_config', {}),
        'volume_path': st.session_state.get('dq_dbfs_path'),
        # Quality controls configuration
        'selected_components': st.session_state.get('dq_selected_components', []),
        'component_configs': st.session_state.get('dq_component_configs', {}),
        'thresholds': st.session_state.get('dq_thresholds', {}),
        'component_enabled': st.session_state.get('dq_component_enabled', {}),
        # Job configuration
        'job_name': st.session_state.get('dq_job_name'),
        'job_description': st.session_state.get('dq_job_description'),
        # Deployment info
        'deployed_job_id': st.session_state.get('dq_deployed_job_id'),
        'deployment_result': st.session_state.get('dq_deployment_result'),
    }


def _compute_project_status() -> str:
    """Derive project lifecycle status from current step and deployment state.

    draft      – step 1 or 2 in progress
    configured – step 3 reached (quality controls done)
    deployed   – deployment result exists
    """
    if st.session_state.get('dq_deployment_result'):
        return 'deployed'
    if st.session_state.get('dq_step', 1) >= 3:
        return 'configured'
    return 'draft'


def _save_to_backend(pid: str, config_data: dict, step_num: int, status_val: str) -> None:
    """Background-thread worker: persist project state to the backend.

    Intentionally has no Streamlit context — uses only stdlib and api_client.
    """
    try:
        print(f"[AutoSave] Starting save for project {pid} at step {step_num}")
        api_client = get_api_client()
        result = api_client.update_project(pid, {'config': config_data, 'step': step_num, 'status': status_val})
        if result.get('status') == 'success':
            AsyncDataLoader.invalidate_cache("dq_projects")
            print(f"[AutoSave] ✅ Successfully saved project {pid} at step {step_num}")
        else:
            print(f"[AutoSave] ⚠️ Save returned non-success: {result}")
    except Exception as e:
        print(f"[AutoSave] ❌ Background save failed: {e}")


def _dispatch_async_save(
    project_id: str, config: dict, step: int, status: str, show_success_message: bool
) -> None:
    """Spawn a non-daemon thread for background save and track it in session state."""
    import threading
    thread = threading.Thread(
        target=_save_to_backend,
        args=(project_id, config, step, status),
        daemon=False,
    )
    thread.start()
    st.session_state.dq_save_thread = thread
    st.session_state.dq_save_pending = True
    if show_success_message:
        st.toast("💾 Saving in background...")


def _dispatch_sync_save(
    project_id: str, config: dict, step: int, status: str, show_success_message: bool
) -> None:
    """Block until the project is saved, then surface success or warning."""
    api_client = get_api_client()
    result = api_client.update_project(project_id, {'config': config, 'step': step, 'status': status})
    if result.get('status') == 'success':
        AsyncDataLoader.invalidate_cache("dq_projects")
        if show_success_message:
            st.toast("Project saved successfully!", icon="✅")
    else:
        st.warning("⚠️ Project state saved locally but sync to database failed.")


def save_project_state(show_success_message=False, async_save=True):
    """Save current workflow state to the active project in database.

    Args:
        show_success_message: If True, shows a success message after saving.
        async_save: If True, saves in background without blocking UI (default=True).

    Note: Uses async background saving by default for instant step transitions.
    """
    project_id = st.session_state.get('dq_current_project_id') or st.session_state.get('current_project_id')
    if not project_id or not st.session_state.get('dq_in_project_mode'):
        return

    project = next((p for p in st.session_state.dq_projects if p['id'] == project_id), None)
    if not project:
        return

    config = _build_project_config()
    status = _compute_project_status()
    step = st.session_state.get('dq_step', 1)

    # Update local copy immediately for instant UI feedback
    project['config'] = config
    project['step'] = step
    project['status'] = status
    project['last_modified'] = datetime.now().isoformat()

    if async_save:
        _dispatch_async_save(project_id, config, step, status, show_success_message)
    else:
        _dispatch_sync_save(project_id, config, step, status, show_success_message)


def get_current_project():
    """Get the current active project (optimized with cache)"""
    project_id = st.session_state.get('dq_current_project_id') or st.session_state.get('current_project_id')
    if not project_id:
        return None
    
    # Use cached dict for O(1) lookup instead of O(n) iteration
    if 'dq_projects_dict' not in st.session_state:
        # Build cache dict from projects list
        st.session_state.dq_projects_dict = {p['id']: p for p in st.session_state.get('dq_projects', [])}
    
    return st.session_state.dq_projects_dict.get(project_id)
