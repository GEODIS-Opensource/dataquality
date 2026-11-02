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
Databricks-specific utilities and helpers
"""
import os
import streamlit as st


def is_databricks_environment():
    """Check if running in Databricks environment"""
    # Check for various Databricks environment indicators
    return (os.getenv('DATABRICKS_RUNTIME_VERSION') is not None or
            os.getenv('DATABRICKS_WORKSPACE_URL') is not None or
            'databricksapps.com' in os.getenv('HOSTNAME', '') or
            os.path.exists('/databricks'))


def get_databricks_workspace_url():
    """Get Databricks workspace URL"""
    return os.getenv('DATABRICKS_WORKSPACE_URL', '')


def _get_cached_user():
    """Return cached user from session state if it looks like a valid email"""
    if hasattr(st, 'session_state') and 'current_user' in st.session_state:
        cached_user = st.session_state.current_user
        if cached_user and '@' in str(cached_user):
            return cached_user
    return None


def _get_user_from_experimental_user():
    """Try to get user from Streamlit experimental user (Databricks Apps)"""
    # st.experimental_user was renamed to st.user (removed in newer Streamlit)
    user_info = getattr(st, 'user', None) or getattr(st, 'experimental_user', None)
    if not user_info:
        return None

    if hasattr(user_info, 'email') and user_info.email and '@' in str(user_info.email):
        if 'example.com' not in str(user_info.email):  # Skip placeholder emails
            return user_info.email
    if hasattr(user_info, 'user_name') and user_info.user_name:
        return user_info.user_name
    if hasattr(user_info, 'username') and user_info.username:
        return user_info.username
    return None


def _get_user_from_headers():
    """Try to get user from Databricks Apps forwarded headers"""
    if not (hasattr(st, 'context') and hasattr(st.context, 'headers')):
        return None

    headers = st.context.headers
    for header_name in ('X-Forwarded-Email', 'X-Forwarded-User', 'X-Forwarded-Preferred-Username'):
        if header_name in headers:
            return headers[header_name]
    return None


def _get_user_from_streamlit_context():
    """Try Streamlit-specific detection methods; headers take precedence, matching original behavior"""
    try:
        return _get_user_from_headers() or _get_user_from_experimental_user()
    except Exception:
        return None


def _get_user_from_secrets():
    """Try Streamlit secrets for local development"""
    try:
        if hasattr(st, 'secrets') and 'user_email' in st.secrets:
            return st.secrets['user_email']
    except Exception:
        pass
    return None


def _get_user_from_env():
    """Try environment variables as fallback"""
    return (os.getenv('DATABRICKS_USER_EMAIL') or
            os.getenv('DATABRICKS_USER') or
            os.getenv('USERNAME', 'Unknown User'))


def get_databricks_user():
    """Get current Databricks user email (cached in session state)"""
    cached_user = _get_cached_user()
    if cached_user:
        return cached_user

    user_email = (_get_user_from_streamlit_context() or
                  _get_user_from_secrets() or
                  _get_user_from_env())

    # Cache the result in session state for performance (use current_user key for consistency)
    if hasattr(st, 'session_state'):
        st.session_state.current_user = user_email

    return user_email


def get_databricks_token():
    """Get Databricks personal access token from environment"""
    return os.getenv('DATABRICKS_TOKEN', '')


def format_databricks_url(path):
    """Format a full Databricks URL from a path"""
    workspace_url = get_databricks_workspace_url()
    if workspace_url and path:
        return f"{workspace_url.rstrip('/')}/{path.lstrip('/')}"
    return path
