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
Backend Database Utilities - Unity Catalog Connection
Used ONLY for querying DQ results tables in Unity Catalog (not the app database).
The app database has been migrated to Lakebase PostgreSQL (see database/connection.py).
"""
from databricks import sql
import os
from contextlib import contextmanager
import json
import uuid
import time

# Database configuration - Unity Catalog (for DQ results queries only)
# Centralized in app.yaml via UC_CATALOG / UC_RESULTS_SCHEMA
DB_CONFIG = {
    'server_hostname': os.getenv('DATABRICKS_SERVER_HOSTNAME', ''),
    'http_path': os.getenv('DATABRICKS_HTTP_PATH', ''),
    'catalog': os.getenv('UC_CATALOG', ''),
    'schema': os.getenv('UC_RESULTS_SCHEMA', 'db_gdm_dq_results')
}


@contextmanager
def get_db_connection():
    """
    Context manager for database connections using Azure Service Principal.
    
    Authentication:
    Gets an OAuth token via the Databricks SDK (Service Principal credentials
    are read from ARM_CLIENT_ID / ARM_CLIENT_SECRET / ARM_TENANT_ID env vars).
    """
    import logging
    
    conn_params = {
        'server_hostname': DB_CONFIG['server_hostname'],
        'http_path': DB_CONFIG['http_path']
    }
    
    try:
        from config.databricks_auth import get_access_token
        access_token = get_access_token()
        logging.info(f"[DB Connection] Using Service Principal token (length: {len(access_token)})")
        conn_params['access_token'] = access_token
        conn = sql.connect(**conn_params)
    except Exception as e:
        logging.error(f"[DB Connection] Service Principal auth failed: {e}")
        raise ValueError(f"Failed to authenticate with Service Principal: {e}")
    
    try:
        yield conn
    except Exception as e:
        raise e
    finally:
        conn.close()


def _generate_id():
    """Generate a unique ID using timestamp and UUID"""
    return int(time.time() * 1000000) + (uuid.uuid4().int % 1000000)


# ==================== User Management Functions ====================

def create_or_update_user(email, username=None):
    """
    Create a new user or update last login for existing user
    Returns the user record
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Use fully qualified table name
        full_table = f"{DB_CONFIG['catalog']}.{DB_CONFIG['schema']}.users"
        
        # Escape single quotes in email and username
        email_escaped = email.replace("'", "''")
        username_escaped = username.replace("'", "''") if username else None
        
        # Check if user exists
        cursor.execute(f"SELECT * FROM {full_table} WHERE email = '{email_escaped}'")
        result = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        
        if result:
            # Update existing user (login_count managed by session tracking)
            username_clause = f"'{username_escaped}'" if username_escaped else "username"
            update_query = f"""
                UPDATE {full_table}
                SET last_login_at = CURRENT_TIMESTAMP(),
                    username = COALESCE({username_clause}, username),
                    updated_at = CURRENT_TIMESTAMP()
                WHERE email = '{email_escaped}'
            """
            cursor.execute(update_query)
            
            # Get updated user
            cursor.execute(f"SELECT * FROM {full_table} WHERE email = '{email_escaped}'")
            result = cursor.fetchall()
        else:
            # Generate new ID
            new_id = _generate_id()
            username_val = f"'{username_escaped}'" if username_escaped else "NULL"
            
            # Create new user
            insert_query = f"""
                INSERT INTO {full_table} (id, email, username, first_login_at, last_login_at, login_count, is_active, created_at, updated_at)
                VALUES ({new_id}, '{email_escaped}', {username_val}, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), 1, true, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
            """
            cursor.execute(insert_query)
            
            # Get created user
            cursor.execute(f"SELECT * FROM {full_table} WHERE email = '{email_escaped}'")
            result = cursor.fetchall()
        
        cursor.close()
        
        # Convert result to dict
        if result and len(result) > 0:
            row = result[0]
            return dict(zip(columns, row)) if columns else None
        return None


def get_user_by_email(email):
    """Get user by email"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        full_table = f"{DB_CONFIG['catalog']}.{DB_CONFIG['schema']}.users"
        
        email_escaped = email.replace("'", "''")
        cursor.execute(f"SELECT * FROM {full_table} WHERE email = '{email_escaped}'")
        result = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        cursor.close()
        
        if result and len(result) > 0:
            row = result[0]
            return dict(zip(columns, row)) if columns else None
        return None


def log_activity(user_email, activity_type, activity_description=None, page=None, metadata=None):
    """
    Log user activity
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        full_users_table = f"{DB_CONFIG['catalog']}.{DB_CONFIG['schema']}.users"
        full_activity_table = f"{DB_CONFIG['catalog']}.{DB_CONFIG['schema']}.activity_log"
        
        # Escape single quotes
        user_email_escaped = user_email.replace("'", "''")
        activity_type_escaped = activity_type.replace("'", "''")
        activity_description_escaped = activity_description.replace("'", "''") if activity_description else None
        page_escaped = page.replace("'", "''") if page else None
        
        # Get user_id from email
        cursor.execute(f"SELECT id FROM {full_users_table} WHERE email = '{user_email_escaped}'")
        result = cursor.fetchall()
        
        if result and len(result) > 0:
            user_id = result[0][0]
            
            # Generate new ID for activity log
            activity_id = _generate_id()
            
            # Convert metadata to JSON string if provided
            metadata_str = json.dumps(metadata).replace("'", "''") if metadata else None
            metadata_val = f"'{metadata_str}'" if metadata_str else 'NULL'
            activity_desc_val = f"'{activity_description_escaped}'" if activity_description_escaped else 'NULL'
            page_val = f"'{page_escaped}'" if page_escaped else 'NULL'
            
            insert_query = f"""
                INSERT INTO {full_activity_table} (id, user_id, activity_type, activity_description, page, metadata, created_at)
                VALUES ({activity_id}, {user_id}, '{activity_type_escaped}', {activity_desc_val}, {page_val}, {metadata_val}, CURRENT_TIMESTAMP())
            """
            cursor.execute(insert_query)
            cursor.close()
            return True
        
        cursor.close()
        return False


def create_session(email, user_agent=None, ip_address=None):
    """Create a new user session and return session_id"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            full_users_table = f"{DB_CONFIG['catalog']}.{DB_CONFIG['schema']}.users"
            full_sessions_table = f"{DB_CONFIG['catalog']}.{DB_CONFIG['schema']}.user_sessions"
            
            # Get user_id
            email_escaped = email.replace("'", "''")
            cursor.execute(f"SELECT id FROM {full_users_table} WHERE email = '{email_escaped}'")
            result = cursor.fetchall()
            
            if result and len(result) > 0:
                user_id = result[0][0]
                session_id = _generate_id()
                
                user_agent_val = f"'{user_agent.replace(chr(39), chr(39)+chr(39))}'" if user_agent else 'NULL'
                
                ip_address_val = f"'{ip_address}'" if ip_address else 'NULL'
                
                insert_query = f"""
                    INSERT INTO {full_sessions_table} (id, user_id, session_start, session_end, ip_address, user_agent)
                    VALUES ({session_id}, {user_id}, CURRENT_TIMESTAMP(), NULL, {ip_address_val}, {user_agent_val})
                """
                cursor.execute(insert_query)
                cursor.close()
                return session_id
            
            cursor.close()
            return None
    except Exception as e:
        print(f"Error creating session: {str(e)}")
        return None


def update_login_count(email):
    """Update login count based on number of sessions"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            full_users_table = f"{DB_CONFIG['catalog']}.{DB_CONFIG['schema']}.users"
            full_sessions_table = f"{DB_CONFIG['catalog']}.{DB_CONFIG['schema']}.user_sessions"
            
            email_escaped = email.replace("'", "''")
            
            # Count total sessions for user
            query = f"""
                UPDATE {full_users_table}
                SET login_count = (
                    SELECT COUNT(*) 
                    FROM {full_sessions_table} s
                    WHERE s.user_id = {full_users_table}.id
                ),
                updated_at = CURRENT_TIMESTAMP()
                WHERE email = '{email_escaped}'
            """
            cursor.execute(query)
            cursor.close()
            return True
    except Exception as e:
        print(f"Error updating login count: {str(e)}")
        return False


# ==================== Data Quality Functions ====================

def create_dq_project(user_email, project_name, description, source_type, source_config):
    """Create a new data quality project"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            full_users_table = f"{DB_CONFIG['catalog']}.{DB_CONFIG['schema']}.users"
            full_projects_table = f"{DB_CONFIG['catalog']}.{DB_CONFIG['schema']}.dq_projects"
            
            # Get user_id
            email_escaped = user_email.replace("'", "''")
            cursor.execute(f"SELECT id FROM {full_users_table} WHERE email = '{email_escaped}'")
            result = cursor.fetchall()
            
            if result and len(result) > 0:
                user_id = result[0][0]
                project_id = _generate_id()
                
                insert_query = f"""
                    INSERT INTO {full_projects_table} 
                    (id, user_id, project_name, description, source_type, source_config, status, created_at, updated_at)
                    VALUES ({project_id}, {user_id}, '{project_name.replace("'", "''")}', 
                            '{description.replace("'", "''")}', '{source_type}', '{json.dumps(source_config).replace("'", "''")}',
                            'draft', CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
                """
                cursor.execute(insert_query)
                cursor.close()
                return project_id
            
            cursor.close()
            return None
    except Exception as e:
        print(f"Error creating DQ project: {str(e)}")
        return None


def create_dq_job(project_id, job_config):
    """Create a Databricks job configuration"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            full_jobs_table = f"{DB_CONFIG['catalog']}.{DB_CONFIG['schema']}.dq_jobs"
            
            job_id = _generate_id()
            
            insert_query = f"""
                INSERT INTO {full_jobs_table}
                (id, project_id, job_name, job_description, notification_email, 
                 failure_action, retry_attempts, priority, status, created_at, updated_at)
                VALUES ({job_id}, {project_id}, '{job_config['job_name'].replace("'", "''")}',
                        '{job_config.get('description', '').replace("'", "''")}',
                        '{job_config.get('notification_email', '')}',
                        '{job_config.get('failure_action', 'Alert Only')}',
                        {job_config.get('retry_attempts', 0)},
                        '{job_config.get('priority', 'Medium')}',
                        'pending', CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
            """
            cursor.execute(insert_query)
            cursor.close()
            return job_id
    except Exception as e:
        print(f"Error creating DQ job: {str(e)}")
        return None


def create_dq_task(job_id, task_config, task_order):
    """Create a data quality task (individual check)"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            full_tasks_table = f"{DB_CONFIG['catalog']}.{DB_CONFIG['schema']}.dq_tasks"
            
            task_id = _generate_id()
            task_key = f"task_{task_config['component_id']}_{task_order}"
            
            insert_query = f"""
                INSERT INTO {full_tasks_table}
                (id, job_id, task_key, task_name, component_id, component_name, category,
                 check_config, thresholds, task_order, is_enabled, created_at, updated_at)
                VALUES ({task_id}, {job_id}, '{task_key}', '{task_config['task_name'].replace("'", "''")}',
                        '{task_config['component_id']}', '{task_config['component_name'].replace("'", "''")}',
                        '{task_config['category']}', '{json.dumps(task_config['config']).replace("'", "''")}',
                        '{json.dumps(task_config.get('thresholds', {})).replace("'", "''")}',
                        {task_order}, true, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
            """
            cursor.execute(insert_query)
            cursor.close()
            return task_id
    except Exception as e:
        print(f"Error creating DQ task: {str(e)}")
        return None


def update_job_databricks_info(job_id, databricks_job_id, databricks_job_url):
    """Update job with Databricks job ID and URL after creation"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            full_jobs_table = f"{DB_CONFIG['catalog']}.{DB_CONFIG['schema']}.dq_jobs"
            
            update_query = f"""
                UPDATE {full_jobs_table}
                SET databricks_job_id = {databricks_job_id},
                    databricks_job_url = '{databricks_job_url}',
                    status = 'deployed',
                    updated_at = CURRENT_TIMESTAMP()
                WHERE id = {job_id}
            """
            cursor.execute(update_query)
            cursor.close()
            return True
    except Exception as e:
        print(f"Error updating job Databricks info: {str(e)}")
        return False


def create_dq_execution(job_id, databricks_run_id, run_url, triggered_by, trigger_type):
    """Create a new execution record when job is triggered"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            full_executions_table = f"{DB_CONFIG['catalog']}.{DB_CONFIG['schema']}.dq_executions"
            
            execution_id = _generate_id()
            
            insert_query = f"""
                INSERT INTO {full_executions_table}
                (id, job_id, databricks_run_id, run_url, status, start_time, 
                 triggered_by, trigger_type, created_at)
                VALUES ({execution_id}, {job_id}, {databricks_run_id}, '{run_url}',
                        'running', CURRENT_TIMESTAMP(), '{triggered_by.replace("'", "''")}',
                        '{trigger_type}', CURRENT_TIMESTAMP())
            """
            cursor.execute(insert_query)
            cursor.close()
            return execution_id
    except Exception as e:
        print(f"Error creating DQ execution: {str(e)}")
        return None


def get_user_projects(user_email):
    """Get all projects for a user"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        full_users_table = f"{DB_CONFIG['catalog']}.{DB_CONFIG['schema']}.users"
        full_projects_table = f"{DB_CONFIG['catalog']}.{DB_CONFIG['schema']}.dq_projects"
        
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


def get_job_tasks(job_id):
    """Get all tasks for a job"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        full_table = f"{DB_CONFIG['catalog']}.{DB_CONFIG['schema']}.dq_tasks"
        
        cursor.execute(f"SELECT * FROM {full_table} WHERE job_id = {job_id} ORDER BY task_order")
        results = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        cursor.close()
        
        return [dict(zip(columns, row)) for row in results]


def get_job_executions(job_id, limit=50):
    """Get execution history for a job"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        full_table = f"{DB_CONFIG['catalog']}.{DB_CONFIG['schema']}.dq_executions"
        
        cursor.execute(f"SELECT * FROM {full_table} WHERE job_id = {job_id} ORDER BY start_time DESC LIMIT {limit}")
        results = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        cursor.close()
        
        return [dict(zip(columns, row)) for row in results]


def get_execution_results(execution_id):
    """Get all task results for an execution"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        full_table = f"{DB_CONFIG['catalog']}.{DB_CONFIG['schema']}.dq_task_results"
        
        cursor.execute(f"SELECT * FROM {full_table} WHERE execution_id = {execution_id} ORDER BY start_time")
        results = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        cursor.close()
        
        return [dict(zip(columns, row)) for row in results]
