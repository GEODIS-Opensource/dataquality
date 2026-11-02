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
Project Repository - Database operations for DQ projects
Handles all project-related database queries
"""
import json
import uuid
import time
import logging
from typing import List, Dict, Any, Optional
from database.connection import get_db_connection, DB_CONFIG

logger = logging.getLogger(__name__)


def _full_table(table_name: str) -> str:
    """Return schema-qualified table name for PostgreSQL"""
    return f"{DB_CONFIG['schema']}.{table_name}"


def _generate_id() -> int:
    """Generate a unique ID using timestamp and UUID"""
    return int(time.time() * 1000000) + (uuid.uuid4().int % 1000000)


class ProjectRepository:
    @staticmethod
    def share_project_with_user(project_id: int, user_id: int) -> bool:
        """
        Partage un projet avec un utilisateur (ajoute une ligne dans project_shares)
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                full_table = _full_table('dq_project_shares')
                cursor.execute(
                    f"INSERT INTO {full_table} (project_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (project_id, user_id)
                )
                cursor.close()
                return True
        except Exception as e:
            logger.error(f"Erreur lors du partage du projet: {str(e)}")
            return False

    @staticmethod
    def unshare_project_with_user(project_id: int, user_id: int) -> bool:
        """
        Retire le partage d’un projet pour un utilisateur
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                full_table = _full_table('dq_project_shares')
                cursor.execute(
                    f"DELETE FROM {full_table} WHERE project_id = %s AND user_id = %s",
                    (project_id, user_id)
                )
                cursor.close()
                return True
        except Exception as e:
            logger.error(f"Erreur lors du retrait du partage: {str(e)}")
            return False

    @staticmethod
    def get_projects_shared_with_user(user_id: int) -> List[Dict[str, Any]]:
        """
        Retourne tous les projets partagés avec un utilisateur
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            full_projects = _full_table('dq_projects')
            full_shares = _full_table('dq_project_shares')
            query = f"""
                SELECT p.*
                FROM {full_projects} p
                JOIN {full_shares} s ON p.id = s.project_id
                WHERE s.user_id = %s
                ORDER BY p.created_at DESC
            """
            cursor.execute(query, (user_id,))
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            cursor.close()
            return [dict(zip(columns, row)) for row in results]

    @staticmethod
    def user_has_access_to_project(project_id: int, user_id: int) -> bool:
        """
        Vérifie si un utilisateur est propriétaire ou collaborateur d’un projet
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            full_projects = _full_table('dq_projects')
            full_shares = _full_table('dq_project_shares')
            query = f"""
                SELECT 1 FROM {full_projects} WHERE id = %s AND user_id = %s
                UNION
                SELECT 1 FROM {full_shares} WHERE project_id = %s AND user_id = %s
            """
            cursor.execute(query, (project_id, user_id, project_id, user_id))
            result = cursor.fetchone()
            cursor.close()
            return result is not None
    """Repository for project database operations"""
    
    @staticmethod
    def create_project(user_email: str, project_name: str, description: str, 
                      source_type: str, config: Dict[str, Any]) -> Optional[int]:
        """
        Create a new data quality project
        
        Args:
            user_email: User email address
            project_name: Name of the project
            description: Project description
            source_type: Type of data source
            config: Configuration dictionary
            
        Returns:
            Project ID or None
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                full_users_table = _full_table('users')
                full_projects_table = _full_table('dq_projects')
                
                # Get user_id
                email_escaped = user_email.replace("'", "''")
                user_query = f"SELECT id FROM {full_users_table} WHERE email = '{email_escaped}'"
                logger.info(f"Checking user with query: {user_query}")
                cursor.execute(user_query)
                result = cursor.fetchall()
                
                if result and len(result) > 0:
                    user_id = result[0][0]
                    logger.info(f"User found with id: {user_id}")
                else:
                    # User doesn't exist, create it automatically
                    logger.info(f"User not found, creating new user for: {user_email}")
                    user_id = _generate_id()
                    username = user_email.split('@')[0].replace('.', ' ').title()
                    
                    create_user_query = f"""
                        INSERT INTO {full_users_table}
                        (id, email, username, first_login_at, last_login_at, login_count, is_active, created_at, updated_at)
                        VALUES ({user_id}, '{email_escaped}', '{username}', 
                                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, true,
                                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                    logger.info(f"Creating user with query: {create_user_query}")
                    cursor.execute(create_user_query)
                    logger.info(f"User created successfully with id: {user_id}")
                
                # Now create the project
                project_id = _generate_id()
                
                insert_query = f"""
                    INSERT INTO {full_projects_table} 
                    (id, user_id, project_name, description, source_type, config, status, created_at, updated_at)
                    VALUES ({project_id}, {user_id}, '{project_name.replace("'", "''")}', 
                            '{description.replace("'", "''")}', '{source_type}', '{json.dumps(config).replace("'", "''")}',
                            'draft', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
                logger.info(f"Inserting project with query: {insert_query}")
                cursor.execute(insert_query)
                cursor.close()
                logger.info(f"Project created successfully with id: {project_id}")
                return project_id
                
        except Exception as e:
            logger.error(f"Error creating DQ project: {str(e)}", exc_info=True)
            raise  # Re-raise the exception so it's caught by the service layer
            return None
    
    @staticmethod
    def get_user_projects(user_email: str) -> List[Dict[str, Any]]:
        """
        Get all projects for a user
        
        Args:
            user_email: User email address
            
        Returns:
            List of project dictionaries
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            full_users_table = _full_table('users')
            full_projects_table = _full_table('dq_projects')
            
            email_escaped = user_email.replace("'", "''")
            query = f"""
                SELECT p.* 
                FROM {full_projects_table} p
                JOIN {full_users_table} u ON p.user_id = u.id
                WHERE u.email = '{email_escaped}'
                ORDER BY p.created_at DESC
            """
            cursor.execute(query)
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            cursor.close()
            
            return [dict(zip(columns, row)) for row in results]
    
    @staticmethod
    def get_project_by_id(project_id: int) -> Optional[Dict[str, Any]]:
        """
        Get project by ID, with shared user emails
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            full_projects = _full_table('dq_projects')
            full_shares = _full_table('dq_project_shares')
            full_users = _full_table('users')
            # Get project info
            cursor.execute(f"SELECT * FROM {full_projects} WHERE id = %s", (project_id,))
            result = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            if not result or len(result) == 0:
                cursor.close()
                return None
            project = dict(zip(columns, result[0]))
            # Get shared user emails (exclude owner)
            cursor.execute(f"""
                SELECT u.email FROM {full_shares} s
                JOIN {full_users} u ON s.user_id = u.id
                WHERE s.project_id = %s
            """, (project_id,))
            shared_emails = [row[0] for row in cursor.fetchall()]
            cursor.close()
            project['shared_with'] = shared_emails
            return project
    
    @staticmethod
    def update_project(project_id: int, updates: Dict[str, Any]) -> bool:
        """
        Update project fields, merging config dict if present (append to config['files'] etc.)
        Args:
            project_id: Project ID
            updates: Dictionary of fields to update
        Returns:
            True if successful, False otherwise
        """
        import copy
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                full_table = _full_table('dq_projects')
                # Valid columns that can be updated
                valid_columns = {
                    'project_name', 'description', 'source_type', 
                    'config', 'status', 'files'
                }
                # Filter out invalid columns (now including 'step')
                valid_columns = {
                    'project_name', 'description', 'source_type', 
                    'config', 'status', 'files', 'step'
                }
                filtered_updates = {k: v for k, v in updates.items() if k in valid_columns}
                if not filtered_updates:
                    print(f"Warning: No valid columns to update in: {updates.keys()}")
                    return True  # Nothing to update but not an error
                
                # SIMPLIFIED: Don't merge config, just replace it entirely
                # This avoids JSON parsing errors and is cleaner
                # The frontend sends the complete config each time
                # Build SET clause with proper escaping
                set_clauses = []
                for key, value in filtered_updates.items():
                    if isinstance(value, str):
                        # Escape single quotes and backslashes for SQL
                        escaped_value = value.replace('\\', '\\\\').replace("'", "''")
                        set_clauses.append(f"{key} = '{escaped_value}'")
                    elif isinstance(value, dict):
                        # Convert dict to JSON string and escape properly
                        json_str = json.dumps(value)
                        # Escape backslashes first, then single quotes
                        escaped_json = json_str.replace('\\', '\\\\').replace("'", "''")
                        set_clauses.append(f"{key} = '{escaped_json}'")
                    else:
                        set_clauses.append(f"{key} = {value}")
                set_clauses.append("updated_at = CURRENT_TIMESTAMP")
                set_clause = ", ".join(set_clauses)
                update_query = f"UPDATE {full_table} SET {set_clause} WHERE id = {project_id}"
                
                print(f"DEBUG: Executing update query: {update_query}")
                cursor.execute(update_query)
                cursor.close()
                return True
                
        except Exception as e:
            print(f"Error updating project: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    @staticmethod
    def delete_project(project_id: int) -> bool:
        """
        Delete a project and all its related records.
        Cascade order (FK constraints):
          dq_alerts, dq_task_results → dq_executions
          dq_executions, dq_tasks, dq_schedules, dq_notebooks, dq_dashboards → dq_jobs
          dq_jobs → dq_projects
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                project_id = int(project_id)

                # 1. Get all job IDs for this project
                cursor.execute(f"SELECT id FROM {_full_table('dq_jobs')} WHERE project_id = {project_id}")
                job_ids = [row[0] for row in cursor.fetchall()]

                if job_ids:
                    ids_str = ','.join(str(i) for i in job_ids)

                    # 2. Delete records referencing dq_executions
                    cursor.execute(
                        f"DELETE FROM {_full_table('dq_alerts')} WHERE execution_id IN "
                        f"(SELECT id FROM {_full_table('dq_executions')} WHERE job_id IN ({ids_str}))"
                    )
                    cursor.execute(
                        f"DELETE FROM {_full_table('dq_task_results')} WHERE execution_id IN "
                        f"(SELECT id FROM {_full_table('dq_executions')} WHERE job_id IN ({ids_str}))"
                    )

                    # 3. Delete records referencing dq_jobs
                    cursor.execute(f"DELETE FROM {_full_table('dq_executions')} WHERE job_id IN ({ids_str})")
                    cursor.execute(f"DELETE FROM {_full_table('dq_tasks')} WHERE job_id IN ({ids_str})")
                    cursor.execute(f"DELETE FROM {_full_table('dq_schedules')} WHERE job_id IN ({ids_str})")
                    cursor.execute(f"DELETE FROM {_full_table('dq_notebooks')} WHERE job_id IN ({ids_str})")
                    cursor.execute(f"DELETE FROM {_full_table('dq_dashboards')} WHERE job_id IN ({ids_str})")

                    # 4. Delete the jobs
                    cursor.execute(f"DELETE FROM {_full_table('dq_jobs')} WHERE project_id = {project_id}")

                # 5. Finally delete the project
                cursor.execute(f"DELETE FROM {_full_table('dq_projects')} WHERE id = {project_id}")
                cursor.close()
                logger.info(f"Successfully deleted project {project_id} and {len(job_ids)} job(s)")
                return True
        except Exception as e:
            logger.error(f"Error deleting project {project_id}: {str(e)}", exc_info=True)
            return False
