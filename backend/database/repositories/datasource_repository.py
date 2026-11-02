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
Datasource Repository - Handles all database operations for CSV and other data sources
"""
from typing import Any, Dict
from database.connection import get_db_connection, DB_CONFIG


def _full_table(table_name: str) -> str:
    """Return schema-qualified table name for PostgreSQL"""
    return f"{DB_CONFIG['schema']}.{table_name}"


class DatasourceRepository:
    def update_project_config(self, project_id: int, config: Dict[str, Any]) -> bool:
        """
        Update the config field for a project in the database.
        """
        import json
        try:
            full_table = _full_table('dq_projects')
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"UPDATE {full_table} SET config = %s WHERE id = %s",
                        (json.dumps(config), project_id)
                    )
            return True
        except Exception as e:
            print(f"Failed to update project config: {e}")
            return False

    def get_project_config(self, project_id: int) -> Dict[str, Any]:
        """
        Retrieve the config field for a project from the database.
        """
        import json
        try:
            full_table = _full_table('dq_projects')
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"SELECT config FROM {full_table} WHERE id = %s",
                        (project_id,)
                    )
                    row = cursor.fetchone()
                    if row and row[0]:
                        return json.loads(row[0])
                    return {}
        except Exception as e:
            print(f"Failed to fetch project config: {e}")
            return {}
