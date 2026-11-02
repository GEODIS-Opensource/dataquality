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
Session State Management for Data Quality Module

Centralizes all session state initialization and access for the DQ workflow.
"""

import streamlit as st
import logging

# Configure logging
logger = logging.getLogger(__name__)


# Default values for every DQ session-state key.
# Defined at module level so other modules can inspect them if needed.
_DQ_SESSION_DEFAULTS: dict = {
    # Navigation
    'dq_view_mode': 'projects',
    'dq_step': 1,
    'dq_max_step_reached': 1,
    # Data source
    'dq_source_type': None,
    'dq_uploaded_file': None,
    'dq_dataset_preview': None,
    'dq_dataset_name': None,
    # Quality controls
    'dq_quality_controls': {},
    'dq_selected_components': [],
    'dq_component_configs': {},
    'dq_thresholds': {},
    'dq_component_enabled': {},
    # Source configuration
    'dq_source_config': None,
    'dq_catalog': None,
    'dq_schema': None,
    'dq_table': None,
    'dq_unity_catalog': None,
    'dq_unity_schema': None,
    'dq_unity_table': None,
    'dq_dbfs_path': None,
    'dq_file_name': None,
    'dq_df_columns_cache': None,
    # CSV flags
    'existing_csv_loaded': False,
    'selected_csv_name': None,
    'selected_csv_path': None,
    # Deployment
    'dq_deployment_result': None,
    'dq_deployed_job_id': None,
    'dq_run_count': 0,
    'dq_last_execution': None,
    # Project management
    'dq_projects': [],
    'dq_in_project_mode': False,
    'current_project_id': None,
    'dq_current_project_id': None,
}


def initialize_session_state():
    """Initialize all session state variables for the data quality workflow."""
    for key, default in _DQ_SESSION_DEFAULTS.items():
        st.session_state.setdefault(key, default)


def reset_session_state():
    """Reset all data quality session state"""
    logger.info("[SESSION] 🧹 Resetting ALL session state for new job")
    
    # Reset to default values
    st.session_state.dq_step = 1
    st.session_state.dq_max_step_reached = 1  # Lock all steps except Step 1
    st.session_state.dq_source_type = None
    st.session_state.dq_uploaded_file = None
    st.session_state.dq_dataset_preview = None
    st.session_state.dq_dataset_name = None
    st.session_state.dq_quality_controls = {}
    st.session_state.dq_selected_components = []
    st.session_state.dq_component_configs = {}
    st.session_state.dq_thresholds = {}
    st.session_state.dq_component_enabled = {}
    
    # Clear job name and description
    st.session_state.dq_job_name = None
    st.session_state.dq_job_description = None
    
    # Clear ALL deployment-related state (CRITICAL for new jobs)
    st.session_state.dq_deployment_result = None
    st.session_state.dq_deployed_job_id = None
    st.session_state.dq_run_count = 0
    st.session_state.dq_last_execution = None
    
    # Clear Databricks-specific fields
    if 'databricks_job_id' in st.session_state:
        del st.session_state['databricks_job_id']
    if 'databricks_job_url' in st.session_state:
        del st.session_state['databricks_job_url']
    if 'workspace_path' in st.session_state:
        del st.session_state['workspace_path']
    
    # Clear any run history or status
    if 'dq_run_history' in st.session_state:
        st.session_state.dq_run_history = []
    if 'dq_last_run_status' in st.session_state:
        st.session_state.dq_last_run_status = None
    if 'dq_last_run_date' in st.session_state:
        st.session_state.dq_last_run_date = None
    
    # Clear source configuration fields (set to None or {} to avoid AttributeError)
    st.session_state.dq_source_config = {}  # Empty dict instead of None
    st.session_state.dq_catalog = None
    st.session_state.dq_schema = None
    st.session_state.dq_table = None
    st.session_state.dq_unity_catalog = None
    st.session_state.dq_unity_schema = None
    st.session_state.dq_unity_table = None
    st.session_state.dq_dbfs_path = None
    st.session_state.dq_file_name = None
    st.session_state.dq_df_columns_cache = None
    
    # Clear CSV-related flags
    st.session_state.existing_csv_loaded = False
    st.session_state.selected_csv_name = None
    st.session_state.selected_csv_path = None
    
    logger.info("[SESSION] ✅ Session state reset complete - ready for new job")


def reset_session_state_full():
    """Reset ALL session state, including navigation and workflow context."""
    st.session_state.clear()
    initialize_session_state()


def get_dataset():
    """Get current dataset from session state"""
    return st.session_state.dq_dataset_preview


def get_dataset_name():
    """Get current dataset name from session state"""
    return st.session_state.get('dq_dataset_name', 'Dataset')


def set_step(step_number):
    """Navigate to a specific step"""
    st.session_state.dq_step = step_number
    # Update URL parameter if in workflow mode
    if st.session_state.get('dq_view_mode') == 'workflow':
        project_id = st.session_state.get('dq_current_project_id')
        job_id = st.session_state.get('dq_current_job_id')
        if project_id and job_id:
            st.query_params.update({
                'view_mode': 'workflow',
                'project_id': str(project_id),
                'job_id': str(job_id),
                'step': str(step_number)
            })
