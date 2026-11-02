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
Datasource Service - Business logic for data source operations
Handles Starburst/Trino and CSV operations
"""
import trino.dbapi
import trino.auth
from typing import List, Dict, Any, Optional
from config.settings import get_settings
from database.repositories import DatasourceRepository
from database.repositories import ProjectRepository
import logging
import os
from urllib.parse import quote as _url_quote


_UC_OBO_REQUIRED_MSG = "Unity Catalog access requires on-behalf-of (OBO) authentication. Please log in again to grant the required permissions."
_UC_INVALID_SCOPE = "Invalid scope"
_UC_REQUIRED_SCOPES = "required scopes: unity-catalog"
_UC_SQL_SCOPE_MSG = (
    "Unity Catalog access requires the 'sql' authorization scope. "
    "Please contact your admin to add the 'sql' scope to this app and restart it."
)
_UC_SCOPE_MISSING_LOG = "[Unity Catalog] OBO token missing 'sql' scope"
_PREVIEW_PERMISSION_DENIED_MSG = (
    "❌ You do not have SELECT permission on table '{table}'. "
    "Please request SELECT privileges from your administrator to access this table."
)


def _empty_preview(columns=None, column_types=None) -> Dict[str, Any]:
    """Preview payload without sample data (optionally keeping the column metadata)."""
    columns = columns or []
    return {
        "columns": columns,
        "column_types": column_types or [],
        "sample_data": [],
        "rows": 0,
        "total_columns": len(columns),
    }


def _preview_error(message: str, **flags) -> Dict[str, Any]:
    return {"status": "error", "message": message, "preview": _empty_preview(), **flags}


def _metadata_only_preview(columns, column_types, message: str) -> Dict[str, Any]:
    return {"status": "success", "preview": _empty_preview(columns, column_types), "message": message}


class DatasourceService:
    """Service for datasource-related operations"""

    def __init__(self):
        self.settings = get_settings()
        self.datasource_repository = DatasourceRepository()
        self.project_repository = ProjectRepository()
    
    def _get_sp_token(self) -> str:
        """Get OAuth token for the app's native SP using Databricks' own M2M OAuth endpoint.
        DATABRICKS_CLIENT_ID/SECRET are Databricks-managed credentials injected by Databricks Apps.
        They are NOT Azure AD app registrations, so azure.identity.ClientSecretCredential cannot
        be used. Instead, call the Databricks OIDC token endpoint directly.
        """
        import requests as _req
        import base64
        client_id = os.getenv('DATABRICKS_CLIENT_ID', '')
        client_secret = os.getenv('DATABRICKS_CLIENT_SECRET', '')
        host = (self.settings.databricks_host or os.getenv('DATABRICKS_HOST', '')).rstrip('/')
        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        resp = _req.post(
            f"{host}/oidc/v1/token",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data="grant_type=client_credentials&scope=all-apis",
        )
        if resp.status_code != 200:
            raise Exception(f"Databricks M2M token failed ({resp.status_code}): {resp.text}")
        return resp.json()["access_token"]

    def _get_workspace_client(self, user_token: str = None):
        """Create WorkspaceClient with optional user token for user-context authentication
        
        Args:
            user_token: Optional user authentication token. If provided, API calls will run
                       with the user's identity and privileges. If not provided, uses default
                       service principal authentication.
        
        Returns:
            WorkspaceClient instance
        """
        from databricks.sdk import WorkspaceClient
        
        if user_token:
            # Use user's token for OBO authentication
            # Must temporarily remove SP env vars to prevent conflict
            host = self.settings.databricks_host or os.getenv('DATABRICKS_HOST')
            logging.info(f"[Auth] Creating WorkspaceClient with user token (OBO) for host: {host}")
            
            # Save and remove ALL credential env vars that would conflict with the user PAT token.
            # Databricks Apps injects DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET (OAuth M2M)
            # in addition to any ARM_* vars we set. The SDK raises
            # "more than one authorization method configured: oauth and pat" if both are present.
            keys_to_clear = (
                'DATABRICKS_CLIENT_ID', 'DATABRICKS_CLIENT_SECRET',
                'DATABRICKS_TOKEN',
                'ARM_CLIENT_ID', 'ARM_CLIENT_SECRET', 'ARM_TENANT_ID',
            )
            saved = {k: os.environ.pop(k) for k in keys_to_clear if k in os.environ}

            try:
                wc = WorkspaceClient(host=host, token=user_token)
                return wc
            finally:
                os.environ.update(saved)
        else:
            # Use Service Principal authentication
            logging.debug("[Auth] Creating WorkspaceClient with Service Principal")
            from config.databricks_auth import get_workspace_client
            return get_workspace_client()
    
    def _get_trino_connection(self):
        """Get Trino/Starburst database connection"""
        return trino.dbapi.connect(
            host=self.settings.trino_host,
            port=self.settings.trino_port,
            user=self.settings.trino_user,
            http_scheme='https',
            auth=trino.auth.BasicAuthentication(
                self.settings.trino_user,
                self.settings.trino_password
            )
        )
    
    def get_catalogs(self) -> Dict[str, Any]:
        """
        Get available Starburst/Trino catalogs
        
        Returns:
            Dictionary with status and list of catalogs
        """
        try:
            conn = self._get_trino_connection()
            cursor = conn.cursor()
            cursor.execute("SHOW CATALOGS")
            catalogs = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            
            return {
                "status": "success",
                "catalogs": catalogs
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to fetch catalogs: {str(e)}",
                "catalogs": []
            }
    
    def get_schemas(self, catalog: str) -> Dict[str, Any]:
        """
        Get schemas in a catalog
        
        Args:
            catalog: Catalog name
            
        Returns:
            Dictionary with status and list of schemas
        """
        try:
            conn = self._get_trino_connection()
            cursor = conn.cursor()
            cursor.execute(f"SHOW SCHEMAS FROM {catalog}")
            schemas = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            
            return {
                "status": "success",
                "schemas": schemas
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to fetch schemas: {str(e)}",
                "schemas": []
            }
    
    def get_tables(self, catalog: str, schema: str) -> Dict[str, Any]:
        """
        Get tables in a schema
        
        Args:
            catalog: Catalog name
            schema: Schema name
            
        Returns:
            Dictionary with status and list of tables
        """
        try:
            conn = self._get_trino_connection()
            cursor = conn.cursor()
            cursor.execute(f"SHOW TABLES FROM {catalog}.{schema}")
            tables = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            
            return {
                "status": "success",
                "tables": tables
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to fetch tables: {str(e)}",
                "tables": []
            }
    
    def preview_table(self, catalog: str, schema: str, table: str) -> Dict[str, Any]:
        """
        Preview table data
        
        Args:
            catalog: Catalog name
            schema: Schema name
            table: Table name
            
        Returns:
            Dictionary with status and preview data
        """
        try:
            conn = self._get_trino_connection()
            cursor = conn.cursor()
            
            # Get column info
            cursor.execute(f"DESCRIBE {catalog}.{schema}.{table}")
            columns = [row[0] for row in cursor.fetchall()]
            
            # Get sample data
            cursor.execute(f"SELECT * FROM {catalog}.{schema}.{table} LIMIT 10")
            rows = cursor.fetchall()
            
            # Convert to list of dicts
            sample_data = [dict(zip(columns, row)) for row in rows]
            
            cursor.close()
            conn.close()
            
            return {
                "status": "success",
                "preview": {
                    "columns": columns,
                    "rows": len(rows),
                    "sample_data": sample_data
                }
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to preview table: {str(e)}",
                "preview": {
                    "columns": [],
                    "rows": 0,
                    "sample_data": []
                }
            }
    
    def upload_csv(self, project_id: int, filename: str, content: bytes, config: str, user_email: str = '') -> Dict[str, Any]:
        """
        Upload CSV file to UC Volume and update project config in DB
        """
        import json
        from io import BytesIO, StringIO
        from databricks.sdk import WorkspaceClient
        from datetime import datetime
        import pandas as pd
        try:
            logging.info(f"[upload_csv] Start upload for project_id={project_id}, filename={filename}")
            username = user_email.split('@')[0] if user_email and '@' in user_email else user_email or 'unknown'
            volume_root = self.settings.uc_upload_volume.rstrip('/')
            volume_path = (f"{volume_root}/"
                           f"{_url_quote(username, safe='')}/"
                           f"{_url_quote(str(project_id), safe='')}/"
                           f"{_url_quote(filename, safe='')}")
            import requests as _requests
            _token = self._get_sp_token()
            _host = (self.settings.databricks_host or os.getenv('DATABRICKS_HOST', '')).rstrip('/')
            _resp = _requests.put(
                f"{_host}/api/2.0/fs/files{volume_path}",
                data=content,
                headers={"Authorization": f"Bearer {_token}", "Content-Type": "application/octet-stream"},
                params={"overwrite": "true"}
            )
            if _resp.status_code not in (200, 204):
                raise Exception(f"Volume upload failed ({_resp.status_code}): {_resp.text}")
            logging.info(f"[upload_csv] Uploaded file to Volume at {volume_path}")
            # Enrich config with file metadata and manage files list inside config
            config_dict = json.loads(config) if isinstance(config, str) else config
            file_meta = {
                'volume_path': volume_path,
                'uploaded_at': datetime.now().isoformat(),
                'file_name': filename,
                'file_size': len(content),
                'source_type': 'csv'
            }
            # Try to extract columns and row count
            try:
                separator = config_dict.get('separator', ',')
                if separator == 'Tab':
                    separator = '\t'
                quote_char = config_dict.get('quote_char', '"')
                skip_lines = config_dict.get('skip_lines', 0)
                has_header = config_dict.get('has_header', True)
                df = pd.read_csv(
                    StringIO(content.decode('utf-8')),
                    sep=separator,
                    quotechar=quote_char,
                    skiprows=skip_lines,
                    nrows=100 if has_header else None,
                    header=0 if has_header else None
                )
                file_meta['columns'] = [str(col) for col in df.columns]
                file_meta['row_count'] = int(len(df))
                file_meta['column_count'] = int(len(df.columns))
                logging.info(f"[upload_csv] Extracted columns: {file_meta['columns']}, row_count: {file_meta['row_count']}, column_count: {file_meta['column_count']}")
            except Exception as meta_e:
                logging.error(f"[upload_csv] Failed to extract CSV metadata: {meta_e}")
                file_meta['columns'] = []
                file_meta['row_count'] = 0
                file_meta['column_count'] = 0
            # Ne PAS stocker en DB ici, juste retourner les métadonnées
            # Le stockage se fera lors du clic "Next: Configure Quality Controls"
            logging.info(f"[upload_csv] Upload to Volume successful, metadata extracted")
            return {
                "status": "success",
                "filename": filename,
                "volume_path": volume_path,
                "size_bytes": len(content),
                "file_metadata": file_meta,  # Retourner les métadonnées pour stockage ultérieur
                "message": "CSV uploaded to Volume successfully (not saved to DB yet)"
            }
        except Exception as e:
            logging.error(f"[upload_csv] Exception: {e}")
            return {"status": "error", "message": str(e)}
    
    def save_csv_to_project_config(self, project_id: int, file_metadata: Dict[str, Any], 
                                    separator: str, quote_char: str, has_header: bool, 
                                    skip_lines: int, dataset_name: str) -> Dict[str, Any]:
        """
        Save CSV file metadata to project config (stores only the active file)
        """
        try:
            logging.info(f"[save_csv_to_project_config] Saving file metadata for project {project_id}")
            
            # Récupérer la config existante ou créer une nouvelle
            existing_config = self.datasource_repository.get_project_config(project_id)
            
            # Stocker UN SEUL fichier (remplacement)
            config_dict = {
                'source_type': 'csv',
                'dataset_name': dataset_name,
                'separator': separator,
                'quote_char': quote_char,
                'has_header': has_header,
                'skip_lines': skip_lines,
                'files': [file_metadata],  # UN SEUL fichier
                'active_file': 0  # Toujours 0 car un seul fichier
            }
            
            logging.info(f"[save_csv_to_project_config] Config to save: {config_dict}")
            
            # Sauvegarder en DB
            updated = self.project_repository.update_project(project_id, {'config': config_dict})
            
            if not updated:
                logging.error(f"[save_csv_to_project_config] Failed to update project config")
                return {"status": "error", "message": "Failed to save file metadata to project"}
            
            logging.info(f"[save_csv_to_project_config] File metadata saved successfully")
            return {
                "status": "success",
                "message": "File metadata saved to project successfully"
            }
        
        except Exception as e:
            logging.error(f"[save_csv_to_project_config] Exception: {e}")
            return {"status": "error", "message": str(e)}

    def list_csv_files(self, project_id: int, user_email: str = '') -> Dict[str, Any]:
        """
        List all CSV files for a project in UC Volume
        """
        import requests as _requests
        try:
            token = self._get_sp_token()
            host = (self.settings.databricks_host or os.getenv('DATABRICKS_HOST', '')).rstrip('/')
            username = user_email.split('@')[0] if user_email and '@' in user_email else user_email or 'unknown'
            volume_root = self.settings.uc_upload_volume.rstrip('/')
            folder_path = (f"{volume_root}/"
                           f"{_url_quote(username, safe='')}/"
                           f"{_url_quote(str(project_id), safe='')}")
            file_list = []

            try:
                resp = _requests.get(
                    f"{host}/api/2.0/fs/directories{folder_path}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code == 404:
                    logging.info(f"[list_csv_files] Folder not found (new project?): {folder_path}")
                    return {"status": "success", "files": [], "total": 0}
                if resp.status_code != 200:
                    raise Exception(f"List directory failed ({resp.status_code}): {resp.text}")
                for entry in resp.json().get('contents', []):
                    name = entry.get('name', '')
                    if name.endswith(('.csv', '.txt', '.json')):
                        size_bytes = int(entry.get('file_size', 0) or 0)
                        size_kb = round(size_bytes / 1024, 2) if size_bytes else 0
                        file_list.append({
                            "name": name,
                            "path": entry.get('path', f"{folder_path}/{name}"),
                            "size_bytes": size_bytes,
                            "size_kb": size_kb,
                        })
                        logging.info(f"[list_csv_files] Added file: {name}")
            except Exception as e:
                logging.info(f"[list_csv_files] Folder not found (new project?): {folder_path} — {e}")
                return {"status": "success", "files": [], "total": 0}

            logging.info(f"[list_csv_files] Final file list: {file_list}")
            return {"status": "success", "files": file_list, "total": len(file_list)}
        except Exception as e:
            logging.error(f"[list_csv_files] Unexpected exception: {e}")
            return {"status": "error", "message": str(e), "files": []}

    @staticmethod
    def _clean_preview_value(value):
        """Convert a pandas/numpy cell to a JSON-safe value (NaN/inf become None)."""
        import numpy as np
        import pandas as pd
        if pd.isna(value) or value is None:
            return None
        if isinstance(value, (np.integer, np.floating)):
            if np.isnan(value) or np.isinf(value):
                return None
            return float(value) if isinstance(value, np.floating) else int(value)
        return value

    def preview_csv(self, project_id: int, file_path: str) -> Dict[str, Any]:
        """
        Preview CSV file from UC Volume for a project, using config from DB
        """
        import requests as _requests
        import pandas as pd
        from io import StringIO
        try:
            token = self._get_sp_token()
            host = (self.settings.databricks_host or os.getenv('DATABRICKS_HOST', '')).rstrip('/')
            resp = _requests.get(
                f"{host}/api/2.0/fs/files{_url_quote(file_path, safe='/')}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code != 200:
                raise Exception(f"File download failed ({resp.status_code}): {resp.text}")
            content_bytes = resp.content
            content_str = content_bytes.decode('utf-8')
            # Fetch config from DB using repository
            existing_config = self.datasource_repository.get_project_config(project_id)
            separator = existing_config.get('separator', ',')
            if separator == 'Tab':
                separator = '\t'
            df = pd.read_csv(
                StringIO(content_str),
                sep=separator,
                quotechar=existing_config.get('quote_char', '"'),
                skiprows=existing_config.get('skip_lines', 0),
                nrows=100
            )
            import numpy as np
            df = df.replace([np.inf, -np.inf], None)
            df = df.where(pd.notnull(df), None)
            preview = [
                {key: self._clean_preview_value(value) for key, value in record.items()}
                for record in df.head(10).to_dict('records')
            ]
            columns = [str(col) for col in df.columns]
            stats = {
                'row_count': int(len(df)),
                'column_count': int(len(df.columns)),
                'columns': columns,
                'file_size': int(len(content_bytes))
            }
            return {
                "status": "success",
                "preview": preview,
                "stats": stats,
                "config": existing_config,
                "file_path": file_path
            }
        except Exception as e:
            return {"status": "error", "message": str(e), "preview": [], "stats": {}}
    
    def delete_csv_file(self, project_id: int, file_path: str, user_email: str) -> Dict[str, Any]:
        """
        Delete CSV file from DBFS (only project owner can delete)
        """
        from databricks.sdk import WorkspaceClient
        try:
            # 1. Vérifier que l'utilisateur est le propriétaire du projet
            project = self.project_repository.get_project_by_id(project_id)
            
            if not project:
                return {"status": "error", "message": "Project not found"}
            
            # 2. Récupérer le user_id du projet
            project_user_id = project.get('user_id')
            
            # 3. Récupérer le user_id de l'utilisateur actuel
            from database.repositories import UserRepository
            user_repo = UserRepository()
            current_user = user_repo.get_user_by_email(user_email)
            
            if not current_user:
                return {"status": "forbidden", "message": "User not found"}
            
            current_user_id = current_user.get('id')
            
            # 4. Vérifier que l'utilisateur est bien le propriétaire
            if current_user_id != project_user_id:
                logging.warning(f"[delete_csv_file] User {user_email} (ID: {current_user_id}) tried to delete file from project {project_id} owned by user ID {project_user_id}")
                return {
                    "status": "forbidden", 
                    "message": "Only the project owner can delete files. You do not have permission to delete this file."
                }
            
            # 5. Supprimer le fichier du Volume
            import requests as _requests
            token = self._get_sp_token()
            host = (self.settings.databricks_host or os.getenv('DATABRICKS_HOST', '')).rstrip('/')
            del_resp = _requests.delete(
                f"{host}/api/2.0/fs/files{_url_quote(file_path, safe='/')}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if del_resp.status_code not in (200, 204):
                raise Exception(f"File delete failed ({del_resp.status_code}): {del_resp.text}")
            logging.info(f"[delete_csv_file] File deleted from Volume: {file_path} by user {user_email}")

            # 6. Mettre à jour la config du projet pour retirer le fichier
            existing_config = self.datasource_repository.get_project_config(project_id)
            files = existing_config.get('files', [])

            # Filtrer pour retirer le fichier supprimé
            updated_files = [f for f in files if f.get('volume_path') != file_path]
            existing_config['files'] = updated_files
            
            # Réajuster active_file si nécessaire
            if len(updated_files) > 0:
                if existing_config.get('active_file', 0) >= len(updated_files):
                    existing_config['active_file'] = len(updated_files) - 1
            else:
                existing_config['active_file'] = -1
            
            # Sauvegarder la config mise à jour
            self.project_repository.update_project(project_id, {'config': existing_config})
            logging.info(f"[delete_csv_file] Project config updated for project {project_id}")
            
            return {
                "status": "success",
                "message": f"File deleted successfully",
                "file_path": file_path
            }
        
        except Exception as e:
            logging.error(f"[delete_csv_file] Exception: {e}")
            return {"status": "error", "message": str(e)}
    
    # ==================== Unity Catalog Methods ====================
    
    @staticmethod
    def _is_scope_error(error: Exception) -> bool:
        """True when the OBO token lacks the authorization scope Unity Catalog needs."""
        message = str(error)
        return _UC_INVALID_SCOPE in message or _UC_REQUIRED_SCOPES in message

    def _list_unity_objects(self, key: str, endpoint: str, user_token: str,
                            fetch, failure_message: str) -> Dict[str, Any]:
        """List Unity Catalog objects with the user's OBO token; Unity Catalog enforces the user's permissions."""
        try:
            if not user_token:
                logging.warning(f"[Unity Catalog] OBO required for {endpoint} endpoint; rejecting service principal fallback")
                return {"status": "error", "message": _UC_OBO_REQUIRED_MSG, key: [], "obo_required": True}

            w = self._get_workspace_client(user_token=user_token)
            names = sorted(fetch(w))
            logging.info(f"[Unity Catalog] User sees {len(names)} {key} (OBO): {names}")
            return {"status": "success", key: names}
        except Exception as e:
            if self._is_scope_error(e):
                logging.error(_UC_SCOPE_MISSING_LOG)
                return {"status": "error", "message": _UC_SQL_SCOPE_MSG, key: [], "scope_error": True}
            logging.error(f"[Unity Catalog] {failure_message}: {str(e)}", exc_info=True)
            return {"status": "error", "message": f"{failure_message}: {str(e)}", key: []}

    def get_unity_catalogs(self, user_token: str = None) -> Dict[str, Any]:
        """Get the Unity Catalog catalogs visible to the user (OBO authentication required)."""
        return self._list_unity_objects(
            "catalogs", "catalogs", user_token,
            lambda w: [c.name for c in w.catalogs.list() if c.name],
            "Failed to fetch Unity Catalog catalogs",
        )

    def get_unity_schemas(self, catalog: str, user_token: str = None) -> Dict[str, Any]:
        """Get the schemas of a catalog visible to the user (OBO authentication required)."""
        return self._list_unity_objects(
            "schemas", f"schemas ({catalog})", user_token,
            lambda w: [s.name for s in w.schemas.list(catalog_name=catalog) if s.name],
            "Failed to fetch schemas",
        )

    def get_unity_tables(self, catalog: str, schema: str, user_token: str = None) -> Dict[str, Any]:
        """Get the tables (views excluded) of a schema visible to the user (OBO authentication required)."""
        return self._list_unity_objects(
            "tables", f"tables ({catalog}.{schema})", user_token,
            lambda w: [
                t.name for t in w.tables.list(catalog_name=catalog, schema_name=schema)
                if t.name and t.table_type != 'VIEW'
            ],
            "Failed to fetch tables",
        )

    def _resolve_warehouse_id(self, w) -> Optional[str]:
        """Warehouse id from the configured http_path, else the first available SQL warehouse."""
        http_path = self.settings.databricks_http_path
        if http_path and '/sql/' in http_path:
            parts = http_path.split('warehouses/')
            if len(parts) > 1 and parts[1].split('/')[0]:
                return parts[1].split('/')[0]
        warehouses = list(w.warehouses.list())
        return warehouses[0].id if warehouses else None

    @staticmethod
    def _has_select_access(privileges) -> bool:
        return any(
            "SELECT" in p or "ALL PRIVILEGES" in p or "ALL_PRIVILEGES" in p or "OWN" in p
            for p in privileges
        )

    def _check_select_privilege(self, w, catalog: str, schema: str, table: str) -> Optional[Dict[str, Any]]:
        """Return a permission error response when the user lacks SELECT on the table, otherwise None."""
        qualified_name = f"{catalog}.{schema}.{table}"
        denied = _preview_error(_PREVIEW_PERMISSION_DENIED_MSG.format(table=qualified_name), permission_error=True)
        try:
            logging.info(f"[Unity Catalog] Checking SELECT privileges on '{qualified_name}'")
            warehouse_id = self._resolve_warehouse_id(w)
            if not warehouse_id:
                logging.warning("[Unity Catalog] No warehouse available for privilege check - skipping")
                return None

            statement = w.statement_execution.execute_statement(
                warehouse_id=warehouse_id,
                statement=f"SHOW GRANTS ON TABLE `{catalog}`.`{schema}`.`{table}`",
                wait_timeout="20s",
                catalog=catalog,
                schema=schema
            )
            rows = statement.result.data_array if statement.result and statement.result.data_array else []
            # Row format: [principal, action_type, object_type, ...]
            privileges = [str(row[1]).upper() if row[1] else "" for row in rows if len(row) >= 2]
            if not self._has_select_access(privileges):
                logging.error(f"[Unity Catalog] User does not have SELECT privilege on '{qualified_name}'")
                return denied
            logging.info(f"[Unity Catalog] Privilege check passed for '{qualified_name}'")
            return None
        except Exception as priv_err:
            error_msg = str(priv_err)
            logging.warning(f"[Unity Catalog] Privilege check failed: {error_msg}")
            # A SHOW GRANTS failure caused by permissions itself indicates a lack of access
            if "PERMISSION" in error_msg.upper() or "DENIED" in error_msg.upper() or "does not have" in error_msg.lower():
                logging.error("[Unity Catalog] Privilege check denied - user lacks access")
                return denied
            logging.info("[Unity Catalog] Privilege check error - continuing with SELECT attempt")
            return None

    @staticmethod
    def _statement_failure(statement, columns, column_types, qualified_name: str) -> Optional[Dict[str, Any]]:
        """Return an error response when the SQL statement failed, otherwise None."""
        from databricks.sdk.service.sql import StatementState
        status = statement.status
        if not status or status.state != StatementState.FAILED:
            return None

        error_msg = getattr(status.error, 'message', None) or "Unknown error"
        logging.error(f"[Unity Catalog] SQL statement FAILED: {error_msg}")
        permission_keywords = ('INSUFFICIENT_PERMISSIONS', 'PERMISSION', 'DENIED', 'PRIVILEGE', 'DOES NOT HAVE SELECT')
        if any(keyword in error_msg.upper() for keyword in permission_keywords):
            return _preview_error(
                f"⛔ Insufficient Permissions: You do not have SELECT privilege on table '{qualified_name}'. "
                "Required permissions: SELECT or ALL PRIVILEGES. Please contact your administrator to grant access.",
                permission_error=True
            )
        return {
            "status": "error",
            "message": f"SQL query failed: {error_msg}",
            "preview": _empty_preview(columns, column_types)
        }

    def _run_preview_query(self, w, warehouse_id: str, catalog: str, schema: str, table: str,
                           limit: int, columns, column_types) -> Dict[str, Any]:
        """Execute the sample query; falls back to column metadata only if it cannot run."""
        qualified_name = f"{catalog}.{schema}.{table}"
        try:
            sql_query = f"SELECT * FROM `{catalog}`.`{schema}`.`{table}` LIMIT {int(limit)}"
            logging.info(f"[Unity Catalog] Executing: {sql_query} on warehouse {warehouse_id}")
            statement = w.statement_execution.execute_statement(
                warehouse_id=warehouse_id,
                statement=sql_query,
                wait_timeout="30s",
                catalog=catalog,
                schema=schema
            )

            failure = self._statement_failure(statement, columns, column_types, qualified_name)
            if failure:
                return failure

            data_array = statement.result.data_array if statement.result and statement.result.data_array else []
            if not data_array:
                logging.warning("[Unity Catalog] No data_array in result - table may be empty or result format unexpected")
            sample_data = [
                {col_name: (row[idx] if idx < len(row) else None) for idx, col_name in enumerate(columns)}
                for row in data_array
            ]
            logging.info(f"[Unity Catalog] Preview successful: {len(sample_data)} rows, {len(columns)} columns")
            return {
                "status": "success",
                "preview": {
                    "columns": columns,
                    "column_types": column_types,
                    "sample_data": sample_data,
                    "rows": len(sample_data),
                    "total_columns": len(columns)
                }
            }
        except Exception as sql_err:
            logging.error(f"[Unity Catalog] SQL execution failed: {sql_err}", exc_info=True)
            return _metadata_only_preview(columns, column_types, f"Column metadata only (SQL query failed: {str(sql_err)})")

    def preview_unity_table(self, catalog: str, schema: str, table: str, limit: int = 10, user_token: str = None) -> Dict[str, Any]:
        """
        Preview data from a Unity Catalog table using SDK Statement Execution
        with the user's OBO credentials.

        Args:
            catalog: Catalog name
            schema: Schema name
            table: Table name
            limit: Number of rows to preview (default 10)
            user_token: User's authentication token for OBO authentication

        Returns:
            Dictionary with status and preview data
        """
        qualified_name = f"{catalog}.{schema}.{table}"
        try:
            if not user_token:
                logging.warning(f"[Unity Catalog] OBO required for preview endpoint ({qualified_name}); rejecting service principal fallback")
                return _preview_error(_UC_OBO_REQUIRED_MSG, obo_required=True)

            logging.info(f"[Unity Catalog] Using OBO authentication for preview of '{qualified_name}'")
            w = self._get_workspace_client(user_token=user_token)
            table_info = w.tables.get(full_name=qualified_name)
            columns = [col.name for col in table_info.columns or []]
            column_types = [col.type_name for col in table_info.columns or []]
            logging.info(f"[Unity Catalog] Got {len(columns)} columns from table metadata")

            denied = self._check_select_privilege(w, catalog, schema, table)
            if denied:
                return denied

            try:
                warehouse_id = self._resolve_warehouse_id(w)
            except Exception as wh_err:
                logging.error(f"[Unity Catalog] Could not list warehouses: {wh_err}")
                return _metadata_only_preview(columns, column_types, "Column metadata only (warehouse lookup failed)")
            if not warehouse_id:
                logging.error("[Unity Catalog] No SQL warehouses available")
                return _metadata_only_preview(
                    columns, column_types, "Column metadata only (no SQL warehouse available for sample data)"
                )

            return self._run_preview_query(w, warehouse_id, catalog, schema, table, limit, columns, column_types)
        except Exception as e:
            if self._is_scope_error(e):
                logging.error(_UC_SCOPE_MISSING_LOG)
                return _preview_error(_UC_SQL_SCOPE_MSG, scope_error=True)
            logging.error(f"[Unity Catalog] Failed to preview '{qualified_name}': {str(e)}", exc_info=True)
            return _preview_error(f"Failed to preview table: {str(e)}")
