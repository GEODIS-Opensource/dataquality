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
API Client for Backend Communication
Handles all HTTP requests to the FastAPI backend
"""
import requests
import os
import streamlit as st
from typing import Optional, Dict, Any, List
import json
import logging
from urllib.parse import quote as _url_quote
from databricks.sdk import WorkspaceClient
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

_PLACEHOLDER_EMAIL_DOMAIN = 'example.com'


class APIClient:
    """Client for communicating with the FastAPI backend"""

    def get_all_users(self) -> list:
        """Get all users (id, email, username)"""
        try:
            response = self.session.get(f"{self.base_url}/api/users", headers=self._get_headers(), timeout=10)
            data = self._handle_response(response)
            return data.get("users", [])
        except Exception as e:
            st.error(f"Failed to fetch users: {str(e)}")
            return []

    def __init__(self, base_url: Optional[str] = None):
        """Initialize API client with base URL"""
        self.base_url = base_url or os.getenv('API_BASE_URL', 'http://localhost:8000')
        self.session = requests.Session()

        # Configure connection pool to prevent connection leaks
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=0,  # No retries to prevent hanging
            pool_block=False
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        # Detect if running in Databricks Apps (backend URL contains 'databricksapps.com')
        self.is_databricks_app = 'databricksapps.com' in self.base_url
    
    @staticmethod
    def _get_or_cache_workspace_client() -> "WorkspaceClient":
        """Return cached WorkspaceClient from session_state, creating it on first call."""
        if hasattr(st, 'session_state') and '_workspace_client' in st.session_state:
            logging.info("[APIClient] Using cached WorkspaceClient")
            return st.session_state._workspace_client
        logging.info("[APIClient] Creating new WorkspaceClient...")
        wc = WorkspaceClient()
        if hasattr(st, 'session_state'):
            st.session_state._workspace_client = wc
        logging.info("[APIClient] Created new WorkspaceClient successfully")
        return wc

    @staticmethod
    def _resolve_logged_in_user(wc: "WorkspaceClient") -> str:
        """Current workspace user name for logging (cached in session state)."""
        if hasattr(st, 'session_state') and '_cached_workspace_user' in st.session_state:
            cached_user = st.session_state._cached_workspace_user
            logging.info(f"[APIClient] Using cached user: {cached_user}")
            return cached_user

        try:
            logged_in_user = wc.current_user.me().user_name
        except Exception as e:
            logging.warning(f"[APIClient] Could not get WorkspaceClient user info: {e}")
            return "unknown"

        if hasattr(st, 'session_state'):
            st.session_state._cached_workspace_user = logged_in_user
        logging.info(f"[APIClient] Logged in user: {logged_in_user}")
        return logged_in_user

    @staticmethod
    def _cache_token(token: str) -> str:
        """Store the token in the Streamlit session (when available) and return it."""
        if hasattr(st, 'session_state'):
            st.session_state._cached_databricks_token = token
        return token

    @staticmethod
    def _extract_token_from_wc(wc: "WorkspaceClient") -> Optional[str]:
        """Extract Databricks token from WorkspaceClient (authenticate → config.token → env)."""
        logged_in_user = APIClient._resolve_logged_in_user(wc)

        logging.info("[APIClient] Calling wc.config.authenticate()...")
        auth_dict = wc.config.authenticate()
        logging.info(f"[APIClient] auth_dict keys: {list(auth_dict.keys()) if auth_dict else 'None'}")

        if auth_dict and 'Authorization' in auth_dict:
            token = auth_dict.get('Authorization', '').replace('Bearer ', '')
            logging.info(f"[APIClient] ✅ Got token from authenticate() for user: {logged_in_user} (length: {len(token)})")
            return APIClient._cache_token(token)

        config_token = getattr(wc.config, 'token', None)
        if config_token:
            logging.info(f"[APIClient] ✅ Got user token from config.token (length: {len(config_token)})")
            return APIClient._cache_token(config_token)

        user_token = os.getenv('DATABRICKS_TOKEN')
        if user_token:
            logging.warning("[APIClient] ⚠️ Using DATABRICKS_TOKEN from environment - this is shared across all users!")
            return user_token

        logging.error(f"[APIClient] ⚠️ Could not extract token. auth_dict: {auth_dict}")
        return None

    def _get_user_token(self) -> Optional[str]:
        """Get the current user's Databricks authentication token (cached per session)."""
        # Priority 1: OBO token cached from main Streamlit thread (usable by background threads
        # because st.context.headers is thread-local and not accessible from ThreadPoolExecutor)
        if hasattr(st, 'session_state') and '_cached_obo_token' in st.session_state:
            obo_token = st.session_state._cached_obo_token
            if obo_token:
                logging.info(f"[APIClient] Using cached OBO token (length: {len(obo_token)})")
                return obo_token

        # Priority 2: WorkspaceClient token cached per session
        if hasattr(st, 'session_state') and '_cached_databricks_token' in st.session_state:
            cached_token = st.session_state._cached_databricks_token
            if cached_token:
                logging.info(f"[APIClient] Using cached WC token (length: {len(cached_token)})")
                return cached_token

        logging.info("[APIClient] No cached token found, attempting to retrieve from WorkspaceClient...")
        try:
            wc = self._get_or_cache_workspace_client()
            return self._extract_token_from_wc(wc)
        except Exception as e:
            logging.error(f"[APIClient] ⚠️ Databricks authentication failed: {str(e)}", exc_info=True)
            return None

    def _get_context_headers_casefold(self) -> Dict[str, str]:
        """Return Streamlit context headers normalized to lowercase keys."""
        try:
            if hasattr(st, 'context') and hasattr(st.context, 'headers') and st.context.headers:
                return {str(k).lower(): str(v) for k, v in st.context.headers.items()}
        except Exception as e:
            logging.warning(f"[APIClient] Could not normalize context headers: {e}")
        return {}

    def _extract_token_from_context_headers(self) -> Optional[str]:
        """Extract user OBO token from Streamlit context headers with robust fallback keys."""
        headers_cf = self._get_context_headers_casefold()
        if not headers_cf:
            return None

        logging.info(f"[APIClient DEBUG] Context headers keys: {list(headers_cf.keys())}")

        # Common Databricks / proxy headers where user token can appear
        for key in (
            "x-forwarded-access-token",
            "x-user-token",
            "x-forwarded-authorization",
            "authorization",
        ):
            raw_value = headers_cf.get(key, "")
            if not raw_value:
                continue
            if raw_value.lower().startswith("bearer "):
                token = raw_value[7:].strip()
            else:
                token = raw_value.strip()
            if token:
                logging.info(f"[APIClient] Found user token in context header '{key}' (length: {len(token)})")
                return token

        return None
        
    def _resolve_obo_token(self) -> Optional[str]:
        """Return OBO token from session cache or context headers, updating the cache on miss."""
        if hasattr(st, 'session_state') and '_cached_obo_token' in st.session_state:
            cached = st.session_state._cached_obo_token
            if cached:
                logging.info(f"[APIClient] Using cached OBO token for request (length: {len(cached)})")
                return cached
        try:
            token = self._extract_token_from_context_headers()
            if token and hasattr(st, 'session_state'):
                st.session_state._cached_obo_token = token
                logging.info("[APIClient] Cached OBO token in session_state")
            return token
        except Exception as e:
            logging.warning(f"[APIClient] Could not access Streamlit context headers: {e}")
            return None

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers for backend API with OBO token"""
        headers = {"Content-Type": "application/json"}

        user_obo_token = self._resolve_obo_token()

        if user_obo_token:
            # Forward user's token to backend using custom header
            # (Databricks may strip x-forwarded-access-token/authorization between apps)
            headers["x-user-token"] = user_obo_token
            logging.info("[APIClient] Added x-user-token header for backend")
            headers["Authorization"] = f"Bearer {user_obo_token}"
            logging.info("[APIClient] Added Authorization header for inter-app auth")
        else:
            logging.warning("[APIClient] No OBO token found in context headers")
            # Fallback: Try WorkspaceClient token
            token = self._get_user_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
                logging.info(f"[APIClient] Added Authorization header from WorkspaceClient (length: {len(token)})")
            else:
                logging.warning("[APIClient] No token available - backend may reject request (401)")

        return headers
    
    def _get_headers_with_auth(self) -> Dict[str, str]:
        """Get request headers with Databricks authentication for job creation"""
        headers = {
            "Content-Type": "application/json"
        }
        logging.info(f"[AUTH] Getting headers with auth for job deployment...")
        token = self._get_user_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
            logging.info(f"[AUTH] ✅ Authorization header added to request")
        else:
            logging.error(f"[AUTH] ❌ No token available - Authorization header NOT added!")
        return headers
    
    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """Handle API response"""
        logging.info(f"Response status: {response.status_code} for URL: {response.url}")
        if response.status_code == 401:
            # Clear all cached tokens so the next Streamlit rerun fetches fresh ones
            logging.warning("[APIClient] 401 Unauthorized — clearing cached tokens")
            if hasattr(st, 'session_state'):
                for _key in ('_cached_obo_token', '_cached_databricks_token',
                             '_workspace_client', '_cached_workspace_user'):
                    st.session_state.pop(_key, None)
        try:
            response.raise_for_status()
            logging.debug(f"Response JSON: {response.text}")
            return response.json()
        except requests.exceptions.HTTPError as e:
            error_detail = "API Error"
            try:
                error_data = response.json()
                error_detail = error_data.get("detail", str(e))
            except Exception:
                error_detail = str(e)
            logging.error(f"API Error: {error_detail} (status {response.status_code})")
            raise Exception(f"API Error: {error_detail}")
        except Exception as e:
            logging.error(f"Request failed: {str(e)}")
            raise Exception(f"Request failed: {str(e)}")
    
    def cleanup(self):
        """Cleanup resources to prevent memory leaks"""
        try:
            if hasattr(self, 'session') and self.session:
                self.session.close()
                logging.debug("API client session closed")
        except Exception as e:
            logging.debug(f"Session cleanup warning: {e}")
    
    @staticmethod
    def _email_from_session_state() -> Optional[str]:
        """Priority 1: session_state.current_user."""
        try:
            if hasattr(st, 'session_state') and 'current_user' in st.session_state:
                email = st.session_state.current_user
                if email and '@' in str(email) and _PLACEHOLDER_EMAIL_DOMAIN not in str(email).lower():
                    return email
        except Exception:
            pass
        return None

    @staticmethod
    def _email_from_experimental_user() -> Optional[str]:
        """Priority 2: st.user (formerly st.experimental_user)."""
        try:
            # st.experimental_user was renamed to st.user (removed in newer Streamlit)
            user_info = getattr(st, 'user', None) or getattr(st, 'experimental_user', None)
            if not user_info:
                return None
            if hasattr(user_info, 'email') and user_info.email and '@' in str(user_info.email):
                if _PLACEHOLDER_EMAIL_DOMAIN not in str(user_info.email).lower():
                    return user_info.email
            if hasattr(user_info, 'user_name') and '@' in str(user_info.user_name):
                return user_info.user_name
            if hasattr(user_info, 'username') and '@' in str(user_info.username):
                return user_info.username
        except Exception:
            pass
        return None

    @staticmethod
    def _email_from_context_headers() -> Optional[str]:
        """Priority 3: forwarded headers."""
        try:
            if hasattr(st, 'context') and hasattr(st.context, 'headers'):
                headers = st.context.headers
                for header in ['X-Forwarded-Email', 'X-Forwarded-User', 'X-Forwarded-Preferred-Username']:
                    if header in headers:
                        return headers[header]
        except Exception:
            pass
        return None

    @staticmethod
    def _email_from_workspace_client() -> Optional[str]:
        """Priority 4: WorkspaceClient (cached in session_state)."""
        try:
            if hasattr(st, 'session_state') and '_workspace_client' in st.session_state:
                wc = st.session_state._workspace_client
            else:
                wc = WorkspaceClient()
                if hasattr(st, 'session_state'):
                    st.session_state._workspace_client = wc
            current_user_info = wc.current_user.me()
            if current_user_info.emails:
                email = current_user_info.emails[0].value
                if email and _PLACEHOLDER_EMAIL_DOMAIN not in str(email).lower():
                    return email
            if hasattr(current_user_info, 'user_name') and current_user_info.user_name:
                if '@' in str(current_user_info.user_name):
                    return current_user_info.user_name
        except Exception:
            pass
        return None

    @staticmethod
    def _email_from_env() -> Optional[str]:
        """Priority 5: environment variables."""
        try:
            email = os.getenv('DATABRICKS_USER_EMAIL') or os.getenv('DATABRICKS_USER')
            if email and '@' in str(email):
                return email
        except Exception:
            pass
        return None

    def _get_user_email(self) -> Optional[str]:
        """Get the current user's email (same logic as get_databricks_user() and home page profile)."""
        email = (
            self._email_from_session_state()
            or self._email_from_experimental_user()
            or self._email_from_context_headers()
            or self._email_from_workspace_client()
            or self._email_from_env()
        )
        if not email:
            logging.error("Could not determine valid user email from any source")
        return email
    
    # ==================== Health & Info ====================
    
    def health_check(self) -> Dict[str, Any]:
        """Check API health"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/",
                headers=self._get_headers(),
                timeout=5
            )
            return self._handle_response(response)
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    # ==================== User Management ====================
    
    def register_user_login(self, email: str, username: Optional[str] = None) -> Dict[str, Any]:
        """Register or update user login"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/users/login",
                headers=self._get_headers(),
                json={"email": email, "username": username},
                timeout=2  # Very short timeout - this is non-critical
            )
            return self._handle_response(response)
        except Exception as e:
            # Silent fail for user tracking - don't disrupt user experience
            return {"status": "error", "message": str(e)}
    
    def get_user(self, email: str) -> Dict[str, Any]:
        """Get user information"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/users/{_url_quote(str(email), safe='')}",
                headers=self._get_headers()
            )
            return self._handle_response(response)
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def log_activity(self, email: str, activity_type: str, description: Optional[str] = None, 
                    page: Optional[str] = None, metadata: Optional[str] = None) -> Dict[str, Any]:
        """Log user activity"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/users/activity",
                headers=self._get_headers(),
                json={
                    "user_email": email,
                    "activity_type": activity_type,
                    "activity_description": description,
                    "page": page,
                    "metadata": metadata
                },
                timeout=5
            )
            return self._handle_response(response)
        except Exception as e:
            # Silent fail for activity logging
            return {"status": "error", "message": str(e)}
    
    # ==================== Projects ====================
    
    def get_projects(self, user_email: str) -> List[Dict[str, Any]]:
        """Get all DQ projects for a user (with retry on timeout)"""
        max_retries = 2
        timeout_seconds = 30
        
        for attempt in range(max_retries):
            try:
                logging.info(f"[API] Fetching projects for {user_email} (attempt {attempt + 1}/{max_retries})")
                response = self.session.get(
                    f"{self.base_url}/api/dq/projects/user/{user_email}",
                    headers=self._get_headers(),
                    timeout=timeout_seconds
                )
                data = self._handle_response(response)
                projects = data.get("projects", [])
                logging.info(f"[API] Successfully fetched {len(projects)} projects")
                return projects
            except requests.exceptions.Timeout:
                logging.warning(f"[API] Timeout on attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    continue  # Retry
                else:
                    st.error(f"⚠️ Backend is taking too long to respond (>{timeout_seconds}s). Please try refreshing.")
                    return []
            except Exception as e:
                logging.error(f"[API] Failed to fetch projects: {str(e)}")
                st.error(f"Failed to fetch projects: {str(e)}")
                return []
        
        return []
    
    def create_project(self, user_email: str, project_name: str, description: str = "", 
                      source_type: str = "unity_catalog", source_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create a new DQ project"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/dq/projects/create",
                headers=self._get_headers(),
                json={
                    "user_email": user_email,
                    "project_name": project_name,
                    "description": description,
                    "source_type": source_type,
                    "source_config": source_config or {}
                },
                timeout=15  # 15s timeout for create operations
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to create project: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def get_project(self, project_id: str) -> Dict[str, Any]:
        """Get project by ID"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/dq/projects/{project_id}",
                headers=self._get_headers()
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to fetch project: {str(e)}")
            return {}
    
    def update_project(self, project_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update project"""
        try:
            response = self.session.put(
                f"{self.base_url}/api/dq/projects/{project_id}",
                headers=self._get_headers(),
                json=updates,
                timeout=10  # 10s timeout
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to update project: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def delete_project(self, project_id: str) -> Dict[str, Any]:
        """Delete project"""
        try:
            response = self.session.delete(
                f"{self.base_url}/api/dq/projects/{project_id}",
                headers=self._get_headers()
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to delete project: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def duplicate_project(self, project_id: str, user_email: str) -> Dict[str, Any]:
        """Duplicate project"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/dq/projects/{project_id}/duplicate",
                headers=self._get_headers(),
                json={"user_email": user_email}
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to duplicate project: {str(e)}")
            return {"status": "error", "message": str(e)}

    def share_project(self, project_id: int, owner_user_id: int, target_user_email: str) -> dict:
        """Share a project with another user by email"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/dq/projects/{project_id}/share",
                headers=self._get_headers(),
                json={"owner_user_id": owner_user_id, "target_user_email": target_user_email},
                timeout=10
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to share project: {str(e)}")
            return {"status": "error", "message": str(e)}

    def unshare_project(self, project_id: int, owner_user_id: int, target_user_email: str) -> dict:
        """Unshare a project for a user by email"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/dq/projects/{project_id}/unshare",
                headers=self._get_headers(),
                json={"owner_user_id": owner_user_id, "target_user_email": target_user_email},
                timeout=10
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to unshare project: {str(e)}")
            return {"status": "error", "message": str(e)}

    def get_projects_shared_with_user(self, user_id: int) -> dict:
        """Get all projects shared with a user"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/dq/projects/shared/{user_id}",
                headers=self._get_headers(),
                timeout=10
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to get shared projects: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def get_project_last_run_report(self, project_id: int) -> Dict[str, Any]:
        """Get last run report for a project"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/dq/projects/{project_id}/last-run-report",
                headers=self._get_headers(),
                timeout=30  # 30s timeout for report fetching
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to fetch last run report: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def download_faulty_records(self, job_id: int) -> bytes:
        """Download faulty records as CSV for a given job"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/dq/jobs/{job_id}/faulty-records/download",
                headers=self._get_headers(),
                timeout=120  # generous timeout for large files
            )
            if response.status_code == 200:
                return response.content
            elif response.status_code == 404:
                # No faulty records available (e.g. all scores are 100%) — not an error
                return None
            else:
                st.error(f"Failed to download faulty records: {response.text}")
                return None
        except Exception as e:
            st.error(f"Failed to download faulty records: {str(e)}")
            return None
    
    # ==================== Jobs (3-Layer Architecture) ====================
    
    def get_project_jobs(self, project_id: int) -> Dict[str, Any]:
        """Get all jobs for a project"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/dq/projects/{project_id}/jobs",
                headers=self._get_headers(),
                timeout=15
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to fetch jobs: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def create_project_job(self, project_id: int, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new job for a project"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/dq/projects/{project_id}/jobs",
                headers=self._get_headers(),
                json=job_data,
                timeout=15
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to create job: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def get_job_details(self, job_id: int) -> Dict[str, Any]:
        """Get job details by ID"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/dq/jobs/{job_id}",
                headers=self._get_headers(),
                timeout=30
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to fetch job details: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def update_job(self, job_id: int, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update job configuration"""
        try:
            response = self.session.put(
                f"{self.base_url}/api/dq/jobs/{job_id}",
                headers=self._get_headers(),
                json=job_data,
                timeout=10
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to update job: {str(e)}")
            return {"status": "error", "message": str(e)}

    def update_job_quiet(self, job_id: int, job_data: Dict[str, Any], timeout: int = 6) -> Dict[str, Any]:
        """Update job configuration without UI errors (safe for async/background calls)."""
        try:
            response = self.session.put(
                f"{self.base_url}/api/dq/jobs/{job_id}",
                headers=self._get_headers(),
                json=job_data,
                timeout=timeout
            )
            return self._handle_response(response)
        except Exception as e:
            logging.warning(f"[API] Quiet update_job failed for job_id={job_id}: {e}")
            return {"status": "error", "message": str(e)}
    
    def delete_job(self, job_id: int) -> Dict[str, Any]:
        """Delete a job"""
        try:
            response = self.session.delete(
                f"{self.base_url}/api/dq/jobs/{job_id}",
                headers=self._get_headers(),
                timeout=10
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to delete job: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def get_job_executions(self, job_id: int, limit: int = 20) -> Dict[str, Any]:
        """Get execution history for a job"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/dq/jobs/{job_id}/executions",
                headers=self._get_headers(),
                params={"limit": limit},
                timeout=15
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to fetch execution history: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    # ==================== Data Sources ====================
    
    def upload_csv(self, project_id: str, file, config: Dict[str, Any], user_email: str = '') -> Dict[str, Any]:
        """Upload CSV file to backend and DBFS"""
        try:
            files = {"file": (file.name, file.getvalue(), "text/csv")}
            data = {
                "config": json.dumps(config)
            }
            headers = self._get_headers()
            headers.pop("Content-Type")  # Let requests set multipart boundary
            response = self.session.post(
                f"{self.base_url}/api/datasources/csv/upload",
                headers=headers,
                params={"project_id": project_id, "user_email": user_email},
                files=files,
                data=data
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to upload CSV: {str(e)}")
            return {"status": "error", "message": str(e)}

    def list_csv_files(self, project_id: int, user_email: str = '') -> List[Dict[str, Any]]:
        """List all CSV files uploaded for a project"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/datasources/csv/list",
                headers=self._get_headers(),
                params={"project_id": project_id, "user_email": user_email},
                timeout=8  # 8s timeout - DBFS listing should be fast
            )
            data = self._handle_response(response)
            return data.get("files", [])
        except Exception as e:
            st.error(f"Failed to list CSV files: {str(e)}")
            return []

    def preview_csv_from_dbfs(self, project_id: int, file_path: str) -> Dict[str, Any]:
        """Preview CSV file from DBFS"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/datasources/csv/preview",
                headers=self._get_headers(),
                params={
                    "project_id": project_id,
                    "file_path": file_path
                }
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to preview CSV: {str(e)}")
            return {"status": "error", "message": str(e)}
        
    def delete_csv_file(self, project_id: int, file_path: str, user_email: str) -> Dict[str, Any]:
        """Delete CSV file from DBFS (only project owner can delete)"""
        try:
            response = self.session.delete(
                f"{self.base_url}/api/datasources/csv/delete",
                headers=self._get_headers(),
                params={
                    "project_id": project_id,
                    "file_path": file_path,
                    "user_email": user_email
                }
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to delete CSV: {str(e)}")
            return {"status": "error", "message": str(e)}
        
    def get_catalogs(self) -> List[str]:
        """Get Unity Catalog catalogs using Databricks SDK with user-level access control"""
        try:
            user_email = self._get_user_email()
            headers = self._get_headers()
            
            # Debug: Log headers being sent
            logging.info(f"[APIClient DEBUG] Request headers keys: {list(headers.keys())}")
            logging.info(f"[APIClient DEBUG] Has x-forwarded-access-token: {'x-forwarded-access-token' in headers}")
            
            response = self.session.get(
                f"{self.base_url}/api/datasources/unity-catalog/catalogs",
                headers=headers,
                params={"user_email": user_email} if user_email else {},
                timeout=15
            )
            data = self._handle_response(response)
            return data.get("catalogs", [])
        except Exception as e:
            st.error(f"Failed to fetch catalogs: {str(e)}")
            return []
    
    def get_schemas(self, catalog: str) -> List[str]:
        """Get schemas in Unity Catalog catalog with user-level access control"""
        try:
            user_email = self._get_user_email()
            params = {"catalog": catalog}
            if user_email:
                params["user_email"] = user_email
            response = self.session.get(
                f"{self.base_url}/api/datasources/unity-catalog/schemas",
                headers=self._get_headers(),
                params=params,
                timeout=15
            )
            data = self._handle_response(response)
            return data.get("schemas", [])
        except Exception as e:
            st.error(f"Failed to fetch schemas: {str(e)}")
            return []
    
    def get_tables(self, catalog: str, schema: str) -> List[str]:
        """Get tables in Unity Catalog schema with user-level access control"""
        try:
            user_email = self._get_user_email()
            params = {"catalog": catalog, "schema": schema}
            if user_email:
                params["user_email"] = user_email
            response = self.session.get(
                f"{self.base_url}/api/datasources/unity-catalog/tables",
                headers=self._get_headers(),
                params=params,
                timeout=15
            )
            data = self._handle_response(response)
            return data.get("tables", [])
        except Exception as e:
            st.error(f"Failed to fetch tables: {str(e)}")
            return []
    
    def preview_table(self, catalog: str, schema: str, table: str) -> Dict[str, Any]:
        """Preview Unity Catalog table data"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/datasources/unity-catalog/preview",
                headers=self._get_headers(),
                json={"catalog": catalog, "schema": schema, "table": table},
                timeout=30
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to preview table: {str(e)}")
            return {"preview": {"columns": [], "rows": 0, "sample_data": []}}
    
    # ==================== Data Quality ====================
    
    def run_job(self, job_id: int, parameters: Dict[str, str] = None) -> Dict[str, Any]:
        """Run a deployed data quality job"""
        try:
            user_email = self._get_user_email()
            logging.info(f"Running job {job_id} triggered by {user_email}")
            
            headers = self._get_headers()
            headers["X-User-Email"] = user_email or "system"
            
            response = self.session.post(
                f"{self.base_url}/api/dq/jobs/{job_id}/run",
                headers=headers,
                json=parameters or {},
                timeout=30
            )
            return self._handle_response(response)
        except Exception as e:
            logging.error(f"Failed to run job: {str(e)}", exc_info=True)
            st.error(f"Failed to run job: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def get_run_status_live(self, job_id: int, run_id: str) -> Dict[str, Any]:
        """Get live status from Databricks for a specific run"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/dq/jobs/{_url_quote(str(job_id), safe='')}/runs/{_url_quote(str(run_id), safe='')}/status",
                headers=self._get_headers(),
                timeout=30
            )
            return self._handle_response(response)
        except Exception as e:
            logging.error(f"Failed to get run status: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def get_run_output(self, job_id: int, run_id: str) -> Dict[str, Any]:
        """Get output and results from a completed run"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/dq/jobs/{job_id}/runs/{run_id}/output",
                headers=self._get_headers(),
                timeout=15
            )
            return self._handle_response(response)
        except Exception as e:
            logging.error(f"Failed to get run output: {str(e)}")
            return {"status": "error", "message": str(e), "results": {}}
    
    def get_execution_history(self, job_id: int, limit: int = 20) -> Dict[str, Any]:
        """Get execution history for a job"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/dq/jobs/{job_id}/executions",
                headers=self._get_headers(),
                params={"limit": limit},
                timeout=30
            )
            return self._handle_response(response)
        except Exception as e:
            logging.error(f"Failed to get execution history: {str(e)}")
            return {"status": "error", "message": str(e), "executions": []}
    
    def get_execution_dashboard(self, execution_id: int) -> Dict[str, Any]:
        """Get dashboard information for a specific execution"""
        try:
            url = f"{self.base_url}/api/dq/executions/{execution_id}/dashboard"
            logging.info(f"[API_CLIENT] GET {url}")
            response = self.session.get(
                url,
                headers=self._get_headers(),
                timeout=10
            )
            logging.info(f"[API_CLIENT] Response status: {response.status_code}")
            result = self._handle_response(response)
            logging.info(f"[API_CLIENT] Response data: {result}")
            return result
        except Exception as e:
            logging.error(f"[API_CLIENT] Failed to get execution dashboard: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"status": "error", "message": str(e)}
    
    def get_job_dashboards(self, job_id: int) -> Dict[str, Any]:
        """Get all dashboards for a job"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/dq/jobs/{job_id}/dashboards",
                headers=self._get_headers(),
                timeout=10
            )
            return self._handle_response(response)
        except Exception as e:
            logging.error(f"Failed to get job dashboards: {str(e)}")
            return {"status": "error", "message": str(e), "dashboards": []}
    
    def schedule_job(self, job_id: int, schedule_config: Dict[str, Any]) -> Dict[str, Any]:
        """Configure schedule for a Databricks job"""
        try:
            logging.info(f"Scheduling job {job_id} with config: {schedule_config}")
            
            response = self.session.post(
                f"{self.base_url}/api/dq/jobs/{job_id}/schedule",
                headers=self._get_headers(),
                json=schedule_config,
                timeout=30
            )
            return self._handle_response(response)
        except Exception as e:
            logging.error(f"Failed to schedule job: {str(e)}", exc_info=True)
            st.error(f"Failed to schedule job: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def execute_dq_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute data quality job (DEPRECATED - use run_job instead)
        
        This endpoint is deprecated. Jobs should be deployed first (Step 3),
        then executed using run_job() method.
        """
        try:
            response = self.session.post(
                f"{self.base_url}/api/dq/execute",
                headers=self._get_headers(),
                json=payload
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to execute DQ job: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get job status"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/dq/jobs/{job_id}/status",
                headers=self._get_headers()
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to get job status: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def get_job_results(self, job_id: str) -> Dict[str, Any]:
        """Get job results"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/dq/jobs/{job_id}/results",
                headers=self._get_headers()
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to get job results: {str(e)}")
            return {"results": {}}
    
    def get_job_report(self, job_id: int) -> Dict[str, Any]:
        """Get job execution report from summary table"""
        try:
            logging.info(f"[APIClient] Fetching report for job {job_id}")
            response = self.session.get(
                f"{self.base_url}/api/dq/jobs/{job_id}/report",
                headers=self._get_headers(),
                timeout=60  # Increased timeout for database queries
            )
            result = self._handle_response(response)
            logging.info(f"[APIClient] Report fetch result: status={result.get('status')}")
            return result
        except Exception as e:
            logging.error(f"[APIClient] Failed to get job report: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "data": []
            }

    def publish_to_openmetadata(self, job_id: int, omd_fqn: str) -> Dict[str, Any]:
        """Publish latest DQ results to OpenMetadata for the given asset FQN."""
        try:
            response = self.session.post(
                f"{self.base_url}/api/dq/jobs/{job_id}/publish-to-openmetadata",
                headers=self._get_headers(),
                json={"omd_fqn": omd_fqn},
                timeout=120,
            )
            return self._handle_response(response)
        except Exception as e:
            logging.error(f"[APIClient] publish_to_openmetadata failed: {e}")
            return {"status": "error", "message": str(e)}

    def update_omd_execution_status(
        self,
        job_id: int,
        exec_id: int,
        status: str,
        columns_pushed: int = None,
        error_message: str = None,
    ) -> Dict[str, Any]:
        """Update the DB status of an OMD execution record."""
        try:
            body = {"status": status}
            if columns_pushed is not None:
                body["columns_pushed"] = columns_pushed
            if error_message is not None:
                body["error_message"] = error_message
            response = self.session.patch(
                f"{self.base_url}/api/dq/jobs/{job_id}/omd-executions/{exec_id}/status",
                headers=self._get_headers(),
                json=body,
                timeout=30,
            )
            return self._handle_response(response)
        except Exception as e:
            logging.error(f"[APIClient] update_omd_execution_status failed: {e}")
            return {"status": "error", "message": str(e)}

    def get_omd_executions(self, job_id: int) -> Dict[str, Any]:
        """Return the OMD publish history for a given DQ job."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/dq/jobs/{job_id}/omd-executions",
                headers=self._get_headers(),
                timeout=30,
            )
            return self._handle_response(response)
        except Exception as e:
            logging.error(f"[APIClient] get_omd_executions failed: {e}")
            return {"status": "error", "message": str(e)}

    def get_omd_latest_status(self, job_id: int) -> Dict[str, Any]:
        """Return the latest OMD push status for a given job (string)."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/dq/jobs/{job_id}/omd-executions/latest-status",
                headers=self._get_headers(),
                timeout=10,
            )
            return self._handle_response(response)
        except Exception as e:
            logging.error(f"[APIClient] get_omd_latest_status failed: {e}")
            return {"status": "error", "message": str(e)}

    def update_omd_fqn(self, job_id: int, omd_fqn: str) -> Dict[str, Any]:
        """Persist or clear the OMD FQN for a job.

        Passing an empty string will clear the stored FQN in the DB.
        """
        try:
            response = self.session.patch(
                f"{self.base_url}/api/dq/jobs/{job_id}/omd-fqn",
                headers=self._get_headers(),
                json={"omd_fqn": omd_fqn},
                timeout=10,
            )
            return self._handle_response(response)
        except Exception as e:
            logging.error(f"[APIClient] update_omd_fqn failed: {e}")
            return {"status": "error", "message": str(e)}

    def deploy_job(self, project_id: int, project_config: Dict[str, Any], 
                   enabled_components: List[str], deployment_config: Dict[str, Any]):
        """
        Deploy data quality job to Databricks with streaming progress updates
        
        Yields status updates in real-time via Server-Sent Events
        """
        try:
            # Get user email for job ownership
            user_email = self._get_user_email()
            
            # Send request with stream=True to get SSE
            response = self.session.post(
                f"{self.base_url}/api/dq/jobs/deploy",
                headers=self._get_headers(),
                json={
                    "project_id": project_id,
                    "project_config": project_config,
                    "enabled_components": enabled_components,
                    "deployment_config": deployment_config,
                    "user_email": user_email
                },
                stream=True,  # Enable streaming
                timeout=120
            )
            
            # Check for HTTP errors
            if response.status_code != 200:
                error_msg = f"Deployment failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_msg)
                except Exception:
                    pass
                yield {"status": "error", "message": error_msg}
                return
            
            # Parse SSE stream
            import json
            for line in response.iter_lines(decode_unicode=True):
                if line:
                    # SSE format: "data: {...}"
                    if line.startswith('data: '):
                        data_str = line[6:]  # Remove "data: " prefix
                        try:
                            update = json.loads(data_str)
                            logging.info(f"SSE update received: {update}")
                            yield update
                        except json.JSONDecodeError as je:
                            logging.error(f"Failed to parse SSE data: {data_str} - Error: {je}")
                            yield {"step": "parse_error", "status": "error", "message": f"Invalid JSON in stream: {data_str[:100]}"}
                    elif line.strip():  # Non-empty non-data line
                        logging.debug(f"SSE non-data line: {line}")
                            
        except Exception as e:
            logging.error(f"Failed to deploy job: {str(e)}", exc_info=True)
            yield {"step": "exception", "status": "error", "message": str(e)}
    
    # ==================== Contracts ====================
    
    def update_ddl(self, table: str, ddl: str) -> Dict[str, Any]:
        """Update table DDL"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/contracts/ddl/update",
                headers=self._get_headers(),
                json={"table": table, "ddl": ddl}
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to update DDL: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def generate_schema(self, schema_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate schema for topic"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/contracts/schema/generate",
                headers=self._get_headers(),
                json=schema_data
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to generate schema: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def get_topics(self) -> List[str]:
        """Get Kafka topics"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/contracts/topics",
                headers=self._get_headers()
            )
            data = self._handle_response(response)
            return data.get("topics", [])
        except Exception as e:
            st.error(f"Failed to fetch topics: {str(e)}")
            return []
    
    # ==================== Monitoring ====================
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get monitoring metrics"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/monitoring/metrics",
                headers=self._get_headers()
            )
            data = self._handle_response(response)
            return data.get("metrics", {})
        except Exception as e:
            st.error(f"Failed to fetch metrics: {str(e)}")
            return {}
    
    def get_system_health(self) -> Dict[str, Any]:
        """Get system health"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/monitoring/health",
                headers=self._get_headers()
            )
            return self._handle_response(response)
        except Exception as e:
            st.error(f"Failed to get system health: {str(e)}")
            return {"components": {}}


# Global API client instance
_api_client = None

def get_api_client() -> APIClient:
    """Get or create API client instance"""
    global _api_client
    if _api_client is None:
        _api_client = APIClient()
    return _api_client
