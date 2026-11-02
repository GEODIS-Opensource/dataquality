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
Lakebase PostgreSQL Connection Management
Handles database connections for Databricks Lakebase PostgreSQL.

Auth: The user's OBO token (captured per-request via a ContextVar in main.py)
is used as the PostgreSQL password. A fresh connection is opened per request
so each request authenticates with its own token.
"""
import psycopg2
import os
import logging
from contextlib import contextmanager
from config.settings import get_settings

logger = logging.getLogger(__name__)

# Get configuration (static params only - password is fetched live per request)
settings = get_settings()

DB_CONFIG = {
    'host': settings.pg_host,
    'port': settings.pg_port,
    'database': settings.pg_database,
    'user': settings.pg_user,
    'schema': settings.pg_schema,
    'sslmode': settings.pg_sslmode,
}


def _get_fresh_password() -> str:
    """
    Get a fresh OAuth token for the Lakebase PostgreSQL password.

    Priority:
    1. PGPASSWORD / PG_PASSWORD env var (injected automatically by Databricks Apps for the service principal)
    2. Databricks SDK fallback
    """
    # 1. Explicit env var overrides (PGPASSWORD auto-injected by Databricks Apps)
    token = os.getenv('PGPASSWORD') or os.getenv('PG_PASSWORD', '')
    if token:
        logger.debug("[Lakebase] Using token from env var.")
        return token

    # 3. Databricks SDK fallback (suppress ARM_* to avoid auth conflict)
    try:
        from databricks.sdk import WorkspaceClient
        saved = {}
        for key in ('ARM_CLIENT_ID', 'ARM_CLIENT_SECRET', 'ARM_TENANT_ID'):
            if key in os.environ:
                saved[key] = os.environ.pop(key)
        try:
            wc = WorkspaceClient()
            headers = wc.config.authenticate()
            auth_header = headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                logger.debug("[Lakebase] Got token via Databricks SDK authenticate().")
                return auth_header[7:]
        finally:
            os.environ.update(saved)
    except Exception as e:
        logger.error(f"[Lakebase] Databricks SDK token fetch failed: {e}")

    logger.error("[Lakebase] All token methods exhausted - no password available.")
    return ''


def _open_connection():
    """Open a fresh psycopg2 connection using the current request token."""
    password = _get_fresh_password()
    if not password:
        raise RuntimeError(
            "[Lakebase] No password available. "
            "Check application logs for token fetch errors."
        )
    conn = psycopg2.connect(
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port'],
        dbname=DB_CONFIG['database'],
        user=DB_CONFIG['user'],
        password=password,
        sslmode=DB_CONFIG['sslmode'],
        options=f"-c search_path={DB_CONFIG['schema']},public"
    )
    conn.autocommit = True
    return conn


@contextmanager
def get_db_connection():
    """
    Context manager that opens a connection per call using the current
    request OBO token and closes it on exit.

    Since OBO tokens are per-user and short-lived, connections are not pooled
    across requests. Opening a connection takes ~10ms on Lakebase.

    Usage:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM table")
    """
    conn = _open_connection()
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


@contextmanager
def get_db_connection_fresh():
    """Alias for get_db_connection() - kept for backwards compatibility."""
    with get_db_connection() as conn:
        yield conn