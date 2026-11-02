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
Data Quality Tool
Access data quality controls and monitoring
"""
import streamlit as st
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import APP_CONFIG, CUSTOM_CSS
from databricks_utils import get_databricks_user, is_databricks_environment
from api_client import APIClient
from data_quality import render as render_data_quality

# Page configuration
st.set_page_config(
    page_title=f"Data Quality - {APP_CONFIG['title']}",
    page_icon="📊",
    layout=APP_CONFIG["layout"],
    initial_sidebar_state="expanded"
)

# Apply custom CSS
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# Ensure API client and user are initialized first
if 'api_client' not in st.session_state:
    st.session_state.api_client = APIClient()
if 'current_user' not in st.session_state:
    st.session_state.current_user = get_databricks_user()

# Prime auth headers once on main thread so OBO token can be reused in worker threads.
try:
    st.session_state.api_client._get_headers()
except Exception:
    pass

# Restore state from URL query parameters on page load
query_params = st.query_params
needs_job_load = False
restored_job_id = None
restored_project_id = None

if 'view_mode' in query_params and 'dq_view_mode' not in st.session_state:
    st.session_state.dq_view_mode = query_params['view_mode']
if 'project_id' in query_params and 'dq_current_project_id' not in st.session_state:
    try:
        restored_project_id = int(query_params['project_id'])
        st.session_state.dq_current_project_id = restored_project_id
    except (ValueError, TypeError):
        pass
if 'job_id' in query_params and 'dq_current_job_id' not in st.session_state:
    try:
        restored_job_id = int(query_params['job_id'])
        st.session_state.dq_current_job_id = restored_job_id
        needs_job_load = True  # Flag to load job configuration
    except (ValueError, TypeError):
        pass
if 'step' in query_params and 'dq_step' not in st.session_state:
    try:
        st.session_state.dq_step = int(query_params['step'])
    except (ValueError, TypeError):
        pass

# Load job configuration if restored from URL
if needs_job_load and restored_job_id and restored_project_id:
    # Import here to avoid circular dependencies
    from data_quality.jobs import load_job_config_from_url
    with st.spinner("Restoring job configuration..."):
        load_job_config_from_url(restored_job_id, restored_project_id)


# Hide the sidebar using CSS
st.markdown("""
    <style>
        [data-testid='stSidebar'] {display: none;}
        .block-container {padding-top: 2rem;}
    </style>
""", unsafe_allow_html=True)

# Render the data quality page
render_data_quality()
