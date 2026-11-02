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
Sidebar component for frontend
"""
import streamlit as st
from config import APP_CONFIG
from databricks_utils import get_databricks_user, is_databricks_environment

def render_sidebar():
    """Render the application sidebar for home page"""
    with st.sidebar:
        st.markdown("## 🚚 Data quality ")
        st.markdown("### Self-Service Portal")
        st.markdown("---")
        
        # ...User Profile section removed...
        
        st.markdown("#### Support")
        st.info(f"📧 {APP_CONFIG['support_email']}\n")
        
        st.markdown("---")
        st.markdown(f"*Version {APP_CONFIG['version']}*")
