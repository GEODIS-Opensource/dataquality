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

"""Step 3: Deploy DQ Job"""

import streamlit as st
import logging
from ..config import get_component_by_id
from ..utils import extract_controlled_columns
from ..payload_generator import generate_dq_payload, format_payload_json, validate_payload
from api_client import get_api_client

logger = logging.getLogger(__name__)

_UNNAMED_PROJECT = "Unnamed Project"


def render_step3_deploy_job():
    """Step 3: Deploy data quality job"""
    # If preview is missing, try to restore it from session state or API
    if st.session_state.get('dq_dataset_preview') is None:
        if st.session_state.get('dq_source_config') or st.session_state.get('dq_source_type') or st.session_state.get('dq_current_job_id'):
            from .step2_configure_controls import _try_restore_dataset_preview
            _try_restore_dataset_preview()

    if st.session_state.dq_dataset_preview is not None:
        dataset_name = st.session_state.get('dq_dataset_name', 'Dataset')
        job_name = st.session_state.get('dq_job_name', 'Unnamed Job')
        
        # Display job info
        st.info(f"📋 **Job:** {job_name} | **Dataset:** {dataset_name}")
        
        # Display existing deployment info if job was previously deployed
        _render_existing_deployment_info()
        
        # Enable/Disable Controls
        _render_control_toggles()
        
        # Summary of enabled controls
        st.markdown("---")
        _render_deployment_summary()
        
        # Navigation
        _render_navigation()
    else:
        st.warning("⚠️ No dataset loaded. Please go back and configure your data source.")
        if st.button("← Back to Data Source"):
            st.session_state.dq_step = 1
            st.rerun()


def _render_existing_deployment_info():
    """Display existing deployment information if job was previously deployed"""
    deployment_result = st.session_state.get('dq_deployment_result')
    
    if deployment_result:
        st.markdown("---")
        st.markdown("#### ✅ Previous Deployment Information")
        st.info("This job has been deployed to Databricks. You can redeploy to update the configuration.")
        
        tasks = deployment_result.get("tasks", [])
        job_url = deployment_result.get("job_url", "")

        col1, col2 = st.columns([1, 1])
        with col1:
            st.metric("Tasks Created", len(tasks))
        with col2:
            if job_url:
                st.link_button("🔗 Open in Databricks", job_url, width="stretch")

        if tasks:
            with st.expander(f"📋 View {len(tasks)} task(s)", expanded=False):
                for task in tasks:
                    st.markdown(f"- `{task.get('task_key', 'Unknown')}`")
        
        st.markdown("---")


def _render_control_toggles():
    """Render enable/disable toggles for each component"""
    st.markdown("#### 🎛️ Enable/Disable Controls")
    st.markdown("Review and enable/disable components before deployment:")
    
    # Initialize component enabled states
    if 'dq_component_enabled' not in st.session_state:
        st.session_state.dq_component_enabled = {}
        # Default all to enabled
        for comp_id in st.session_state.dq_selected_components:
            st.session_state.dq_component_enabled[comp_id] = True
    
    # Display components with enable/disable toggles
    for component_id in st.session_state.dq_selected_components:
        component = get_component_by_id(component_id)
        if component:
            col1, col2, col3 = st.columns([3, 2, 1])
            
            with col1:
                st.markdown(f"**{component['icon']} {component['name']}**")
                st.caption(component['description'])
            
            with col2:
                # Show configured columns
                config = st.session_state.dq_component_configs.get(component_id, {})
                controlled_columns = extract_controlled_columns(config)
                
                if controlled_columns:
                    st.caption(f"📋 Columns: {', '.join([f'`{c}`' for c in controlled_columns])}")
            
            with col3:
                enabled = st.session_state.dq_component_enabled.get(component_id, True)
                if st.checkbox("Enabled", value=enabled, key=f"enable_{component_id}"):
                    st.session_state.dq_component_enabled[component_id] = True
                else:
                    st.session_state.dq_component_enabled[component_id] = False
            
            st.markdown("---")


def _render_deployment_summary():
    """Render deployment summary metrics"""
    st.markdown("#### 📊 Deployment Summary")
    enabled_count = sum(1 for v in st.session_state.dq_component_enabled.values() if v)
    total_count = len(st.session_state.dq_selected_components)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Controls", total_count)
    with col2:
        st.metric("Enabled Controls", enabled_count, delta=f"{enabled_count - (total_count - enabled_count)}")
    with col3:
        st.metric("Disabled Controls", total_count - enabled_count)
    with col4:
        deployment_status = "🟢 Ready" if enabled_count > 0 else "🔴 No Controls"
        st.metric("Status", deployment_status)
    
    if enabled_count == 0:
        st.warning("⚠️ At least one control must be enabled to deploy the job.")
    else:
        # Deploy job button
        st.markdown("---")
        
        # Check if this is a redeployment
        is_redeployment = st.session_state.get('dq_deployment_result') is not None
        
        if is_redeployment:
            st.markdown("#### 🔄 Redeploy DQ Job")
            st.markdown("Update the existing Databricks job with the current configuration. This will update notebooks and task definitions.")
            button_label = "🔄 Redeploy Job"
        else:
            st.markdown("#### 🚀 Deploy DQ Job")
            st.markdown("Deploy this data quality job to Databricks. This will create notebooks and a Databricks job with tasks for each enabled control.")
            button_label = "🚀 Deploy Job"
        
        if st.button(button_label, width="stretch", type="primary"):
            _deploy_job()


# ── Deployment helpers ────────────────────────────────────────────────────────

def _resolve_project_name(project_id: str, api_client) -> str:
    """Return the project name from the API, falling back to the local cache."""
    project_result = api_client.get_project(project_id)
    if project_result.get('status') == 'success':
        return project_result.get('project', {}).get('name', _UNNAMED_PROJECT)
    from ..projects import get_current_project
    current_project = get_current_project()
    return current_project.get('name', _UNNAMED_PROJECT) if current_project else _UNNAMED_PROJECT


def _build_source_path(source_type: str, source_config: dict) -> str:
    """Derive the source path from session state based on *source_type*."""
    if source_type == 'unity_catalog':
        catalog = st.session_state.get('dq_catalog', '')
        schema = st.session_state.get('dq_schema', '')
        table = st.session_state.get('dq_table', '')
        return f"{catalog}.{schema}.{table}" if catalog and schema and table else ''
    # For CSV: source_path = DBFS path
    return st.session_state.get('dq_dbfs_path', source_config.get('dbfs_path', ''))


def _build_project_config(project_name: str, source_config: dict) -> dict:
    """Build the project configuration dict from session state."""
    source_type = st.session_state.get('dq_source_type', 'table')
    return {
        "project_name": project_name,
        "catalog": st.session_state.get('dq_catalog', ''),
        "schema": st.session_state.get('dq_schema', ''),
        "table": st.session_state.get('dq_table', ''),
        "source_type": source_type,
        "source_path": _build_source_path(source_type, source_config),
        "job_name": st.session_state.get('dq_job_name', ''),
        "job_description": st.session_state.get('dq_job_description', ''),
    }


def _collect_enabled_components() -> tuple:
    """Return (enabled_components, component_configs) from session state."""
    enabled_components = []
    component_configs = {}
    for comp_id in st.session_state.dq_selected_components:
        # Default to True if not explicitly set (newly added components should be enabled)
        if st.session_state.dq_component_enabled.get(comp_id, True):
            enabled_components.append(comp_id)
            component_configs[comp_id] = st.session_state.dq_component_configs.get(comp_id, {})
    return enabled_components, component_configs


def _build_deployment_config(component_configs: dict) -> dict:
    """Build the deployment configuration dict from session state."""
    return {
        "job_name": st.session_state.get('dq_job_name', 'Unnamed Job'),
        "job_description": st.session_state.get('dq_job_description', ''),
        "component_configs": component_configs,
        "thresholds": st.session_state.get('dq_thresholds', {}),
        # Pass existing job ID to update instead of creating a duplicate
        "existing_job_id": st.session_state.get('dq_current_job_id'),
    }


def _get_status_icon(status: str) -> str:
    """Map a deployment *status* string to its display icon."""
    if status == 'running':
        return '⏳'
    if status == 'success':
        return '✅'
    if status == 'error':
        return '❌'
    if status == 'warning':
        return '⚠️'
    return '📌'


def _accumulate_update(final_result: dict, update: dict) -> None:
    """Merge relevant fields from a streaming *update* into *final_result*."""
    step = update.get('step', '')
    status = update.get('status', '')
    if step == 'complete' and status == 'success':
        final_result.update(update)
    if step == 'database' and status == 'success':
        final_result['db_job_id'] = update.get('db_job_id')
        final_result['databricks_job_id'] = update.get('databricks_job_id')
        final_result['job_url'] = update.get('job_url', final_result.get('job_url', ''))
    if 'tasks' in update and update['tasks']:
        final_result['tasks'] = update['tasks']
    if 'notebooks' in update and update['notebooks']:
        final_result['notebooks'] = update['notebooks']
    if 'workspace_path' in update:
        final_result['workspace_path'] = update['workspace_path']
    if 'job_url' in update and update['job_url']:
        final_result['job_url'] = update['job_url']
    if 'job_id' in update and update['job_id']:
        final_result['databricks_job_id'] = update['job_id']


def _stream_deployment(api_client, project_id: str, project_config: dict,
                       enabled_components: list, deployment_config: dict,
                       status_container) -> dict | None:
    """Drive the streaming deployment loop and render live progress.

    Returns the accumulated *final_result* dict, or *None* if a hard error
    was received from the API (the error message is already shown to the user).
    """
    final_result = {
        'tasks': [], 'notebooks': [], 'workspace_path': '',
        'job_url': '', 'databricks_job_id': None, 'db_job_id': None,
    }
    deployment_status = {
        'initialization': None, 'notebooks': None, 'tasks': None,
        'job_creation': None, 'permissions': None, 'complete': None,
    }
    task_status: dict = {}

    with status_container.container():
        st.markdown("### 🚀 Deployment Progress")
        progress_bar = st.progress(0)
        status_text = st.empty()
        details_expander = st.expander("📋 Deployment Details", expanded=True)
        with details_expander:
            status_messages = st.empty()

        messages: list = []
        total_steps = 6  # init, notebooks, tasks, job_creation, permissions, complete
        completed_steps = 0

        for update in api_client.deploy_job(
            project_id=project_id,
            project_config=project_config,
            enabled_components=enabled_components,
            deployment_config=deployment_config,
        ):
            if not isinstance(update, dict):
                st.warning(f"⚠️ Received invalid update format: {type(update)} - {str(update)[:100]}")
                continue

            step = update.get('step', '')
            status = update.get('status', '')
            message = update.get('message', '')

            # Update step / task tracking
            if step in deployment_status:
                deployment_status[step] = status
            elif step.startswith('task_'):
                task_key = update.get('task_key', step)
                task_status[task_key] = {'status': status, 'name': update.get('task_name', task_key)}

            icon = _get_status_icon(status)
            if status == 'success' and step in deployment_status:
                completed_steps += 1

            messages.append(f"{icon} **{step.replace('_', ' ').title()}**: {message}")
            progress_bar.progress(min(completed_steps / total_steps, 1.0))
            status_text.markdown(f"**Current Step:** {message}")
            with details_expander:
                status_messages.markdown("\n\n".join(messages[-10:]))  # Show last 10 messages

            _accumulate_update(final_result, update)

            if status == 'error':
                st.error(f"❌ Deployment failed: {message}")
                return None

    return final_result


def _show_deployment_results(final_result: dict) -> None:
    """Render the success UI and persist deployment data to the database."""
    st.toast("Job deployed successfully!", icon="✅")

    with st.expander("📋 Deployment Details", expanded=True):
        col1 = st.columns(1)[0]  # Use full width for left column
        with col1:
            st.metric("Tasks Created", len(final_result.get("tasks", [])))

        if final_result.get("tasks"):
            st.markdown("**Tasks:**")
            for task in final_result["tasks"]:
                st.markdown(f"- `{task.get('task_key', 'Unknown')}`")

    st.info("💡 **Next Steps**: You can now run or schedule this job in Databricks.")

    st.session_state.dq_deployment_result = final_result
    st.session_state.dq_deployed_job_id = (
        final_result.get("db_job_id") or final_result.get("databricks_job_id")
    )

    job_id = st.session_state.get('dq_current_job_id')
    if job_id:
        _save_deployment_to_database(job_id, final_result)
    else:
        st.warning("⚠️ No job ID found - deployment info not saved to database")

    st.toast("Job deployed successfully! Configuration auto-saved.", icon="✅")


# ── Orchestrator ──────────────────────────────────────────────────────────────

def _deploy_job():
    """Deploy data quality job to Databricks with real-time progress."""
    # Note: Project state should be saved manually via "💾 Save" button before deployment
    progress_container = st.empty()
    status_container = st.empty()

    try:
        # Support both old and new session-state key names for project ID
        project_id = st.session_state.get('dq_current_project_id') or st.session_state.get('current_project_id')
        if not project_id:
            st.error("❌ No project selected. Please save your project first.")
            return

        source_config = st.session_state.get('dq_source_config', {})
        api_client = get_api_client()

        project_name = _resolve_project_name(project_id, api_client)
        logger.info(f"[DEPLOY] Using project_name: {project_name}")

        project_config = _build_project_config(project_name, source_config)
        enabled_components, component_configs = _collect_enabled_components()
        deployment_config = _build_deployment_config(component_configs)

        # Debug: Show what will be deployed
        st.info(f"🛠️ **Debug**: Deploying {len(enabled_components)} components: {', '.join(enabled_components)}")

        final_result = _stream_deployment(
            api_client, project_id, project_config, enabled_components, deployment_config, status_container
        )

        progress_container.empty()
        status_container.empty()

        if final_result and final_result.get('databricks_job_id'):
            _show_deployment_results(final_result)
        else:
            st.warning("⚠️ Deployment completed but no result data received.")

    except Exception as e:
        st.error(f"❌ Error deploying job: {str(e)}")
        st.exception(e)


def _save_deployment_to_database(job_id: int, deployment_result: dict):
    """Save deployment configuration to database"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        from api_client import get_api_client
        api_client = get_api_client()
        
        logger.info(f"💾 Saving deployment info to database for job {job_id}")
        logger.info(f"📦 Deployment data keys: {list(deployment_result.keys())}")
        logger.info(f"🔧 Databricks Job ID: {deployment_result.get('databricks_job_id')}")
        logger.info(f"📋 Tasks: {len(deployment_result.get('tasks', []))}")
        logger.info(f"📓 Notebooks: {len(deployment_result.get('notebooks', []))}")
        
        # Update job with deployment info — only safe/known columns
        # deployment_config is excluded intentionally: if the column does not exist in Databricks
        # the entire UPDATE query would fail and status would remain 'configured'
        job_update = {
            'status': 'deployed',
            'databricks_job_id': deployment_result.get('databricks_job_id'),
            'databricks_job_url': deployment_result.get('job_url', ''),
            'workspace_path': deployment_result.get('workspace_path', '')
        }
        
        logger.info(f"📤 Sending update to API with fields: {list(job_update.keys())}")
        result = api_client.update_job(job_id, job_update)
        
        if result.get('status') == 'success':
            logger.info(f"✅ Deployment info saved successfully to database for job {job_id}")
            #st.toast("✅ Deployment info saved to database", icon="✅")
        else:
            error_msg = result.get('message', 'Unknown error')
            logger.error(f"❌ Failed to save deployment info: {error_msg}")
            # Don't show error to user if it's just the missing column - it's not critical
            if 'deployment_config' not in error_msg.lower():
                st.warning(f"⚠️ Failed to save deployment info: {error_msg}")
    except Exception as e:
        error_str = str(e)
        logger.error(f"❌ Error saving deployment info: {error_str}")
        # Only show error if it's not about the missing column
        if 'deployment_config' not in error_str.lower():
            st.error(f"Error saving deployment info: {error_str}")


def _render_navigation():
    """Render navigation buttons with validation and auto-save"""
    st.markdown("---")
    
    # Check if job is deployed
    is_deployed = st.session_state.get('dq_deployed_job_id') is not None
    
    if not is_deployed:
        st.info("💡 You must deploy the job before proceeding to Step 4 (Run or Schedule).")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        # Callback for instant back navigation
        if st.button("← Back to Quality Controls", width="stretch",
                    on_click=lambda: st.session_state.update({'dq_step': 2})):
            pass
    with col2:
        # Only enable Next if job is deployed
        if is_deployed:
            if st.button("Next: Run or Schedule →", type="primary", width="stretch"):
                # Update step - auto-save will happen in main.py after render
                st.session_state.dq_step = 4
                st.rerun()
        else:
            st.button("Next: Run or Schedule →", type="primary", width="stretch", disabled=True,
                     help="Please deploy the job first")
