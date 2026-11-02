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
Centralized Databricks Authentication via Azure Service Principal.

Databricks Apps auto-injects DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET
for its built-in OAuth M2M identity.  We must suppress those so they don't
clash with the Azure SP credentials (ARM_CLIENT_ID, ARM_CLIENT_SECRET,
ARM_TENANT_ID).

This module provides helpers for:
- Getting a WorkspaceClient (SDK operations)
- Getting a Bearer token (REST API calls / SQL connector)
"""
import os
import logging

logger = logging.getLogger(__name__)

_cached_client = None


def get_workspace_client():
    """Return a shared WorkspaceClient using Azure Service Principal credentials.

    Temporarily removes the Databricks-injected DATABRICKS_CLIENT_ID /
    DATABRICKS_CLIENT_SECRET so the SDK only sees the Azure SP auth method.
    """
    global _cached_client
    if _cached_client is not None:
        return _cached_client

    from databricks.sdk import WorkspaceClient

    host = os.getenv('DATABRICKS_HOST') or os.getenv('DATABRICKS_SERVER_HOSTNAME')
    if host and not host.startswith('https://'):
        host = f"https://{host}"

    # Suppress the platform-injected OAuth M2M vars so they don't conflict
    saved = {}
    for key in ('DATABRICKS_CLIENT_ID', 'DATABRICKS_CLIENT_SECRET', 'DATABRICKS_TOKEN'):
        if key in os.environ:
            saved[key] = os.environ.pop(key)

    try:
        logger.info(f"[Auth] Creating WorkspaceClient (Azure SP) for host: {host}")
        _cached_client = WorkspaceClient(
            host=host,
            azure_client_id=os.getenv('ARM_CLIENT_ID'),
            azure_client_secret=os.getenv('ARM_CLIENT_SECRET'),
            azure_tenant_id=os.getenv('ARM_TENANT_ID'),
        )
        try:
            me = _cached_client.current_user.me()
            logger.info(f"[Auth] Authenticated as: {me.display_name} ({me.user_name})")
        except Exception as e:
            logger.warning(f"[Auth] Could not verify identity: {e}")
    finally:
        # Restore the platform vars so other code that needs them still works
        os.environ.update(saved)

    return _cached_client


def get_access_token() -> str:
    """Return a valid access token string (no 'Bearer ' prefix).

    # TEMPORAIRE — PAT token utilisé en attendant que l'admin enregistre
    # le SP Azure (ARM_CLIENT_ID=381b908f-...) au niveau Account Console Databricks.
    # Une fois fait, supprimer DQ_PAT_TOKEN de app.yaml et cette branche if.
    # L'auth reprendra via Azure SP (ARM_CLIENT_ID / ARM_CLIENT_SECRET / ARM_TENANT_ID).
    """
    pat = os.getenv('DQ_PAT_TOKEN')
    if pat:
        logger.info("[Auth] Using PAT token (temporary — pending SP account-level registration)")
        return pat

    wc = get_workspace_client()
    headers = wc.config.authenticate()
    auth_header = headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:]
    token = getattr(wc.config, 'token', None)
    if token:
        return token
    raise RuntimeError("[Auth] Could not obtain access token from Databricks SDK")


def get_host() -> str:
    """Return the plain hostname (no https://)."""
    host = os.getenv('DATABRICKS_SERVER_HOSTNAME') or os.getenv('DATABRICKS_HOST', '')
    return host.replace('https://', '').rstrip('/')
