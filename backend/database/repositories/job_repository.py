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
Job Repository - Database operations for DQ jobs
Handles all job-related database queries
"""
import json
import os
import re
import uuid
import time
from typing import List, Dict, Any, Optional
from database.connection import get_db_connection, get_db_connection_fresh, DB_CONFIG


def _generate_id() -> int:
    """Generate a unique ID using timestamp and UUID"""
    return int(time.time() * 1000000) + (uuid.uuid4().int % 1000000)


def _full_table(table_name: str) -> str:
    """Return schema-qualified table name for PostgreSQL"""
    return f"{DB_CONFIG['schema']}.{table_name}"


import logging as _logging
_repo_logger = _logging.getLogger(__name__)


class JobRepository:
    """Repository for job database operations"""
    
    @staticmethod
    def create_job(project_id: int, job_config: Dict[str, Any]) -> Optional[int]:
        """
        Create a Databricks job configuration
        
        Args:
            project_id: Project ID
            job_config: Job configuration dictionary
            
        Returns:
            Job ID or None
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                full_jobs_table = _full_table('dq_jobs')
                job_id = _generate_id()

                insert_query = f"""
                    INSERT INTO {full_jobs_table}
                    (id, project_id, job_name, job_description, workspace_path, notification_email, 
                     failure_action, retry_attempts, priority, status,
                     step, source_type, source_config, quality_config, 
                     schedule_cron, schedule_timezone, deployed_by, run_count, is_primary,
                     created_at, updated_at)
                    VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                """
                cursor.execute(insert_query, JobRepository._job_insert_params(job_id, project_id, job_config))
                cursor.close()
                return job_id
        except Exception as e:
            print(f"Error creating DQ job: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    @staticmethod
    def _job_insert_params(job_id: int, project_id: int, job_config: Dict[str, Any]) -> tuple:
        """Values for the dq_jobs INSERT; empty optional values are stored as NULL."""
        source_config = job_config.get('source_config')
        quality_config = job_config.get('quality_config')
        return (
            job_id,
            project_id,
            job_config.get('job_name') or f'dq_job_{project_id}',
            job_config.get('description') or None,
            job_config.get('workspace_path') or None,
            job_config.get('notification_email') or None,
            job_config.get('failure_action') or 'Alert Only',
            job_config.get('retry_attempts') or 0,
            job_config.get('priority') or 'Medium',
            job_config.get('status', 'pending'),  # Support custom status (e.g., 'draft')
            job_config.get('step', 1),
            job_config.get('source_type', 'table') or None,
            json.dumps(source_config) if source_config else None,
            json.dumps(quality_config) if quality_config else None,
            job_config.get('schedule_cron') or None,
            job_config.get('schedule_timezone', 'UTC'),
            job_config.get('deployed_by', '') or None,
            job_config.get('run_count', 0),
            bool(job_config.get('is_primary', False)),
        )
    
    @staticmethod
    def create_task(job_id: int, task_config: Dict[str, Any], task_order: int) -> Optional[int]:
        """
        Create a data quality task (individual check)
        
        Args:
            job_id: Job ID
            task_config: Task configuration dictionary
            task_order: Order of task in job
            
        Returns:
            Task ID or None
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                full_tasks_table = _full_table('dq_tasks')
                
                task_id = _generate_id()
                task_key = f"task_{task_config['component_id']}_{task_order}"
                notebook_path = task_config.get('notebook_path', '')
                
                insert_query = f"""
                    INSERT INTO {full_tasks_table}
                    (id, job_id, task_key, task_name, component_id, component_name, category,
                     notebook_path, check_config, thresholds, task_order, is_enabled, created_at, updated_at)
                    VALUES ({task_id}, {job_id}, '{task_key}', '{task_config['task_name'].replace("'", "''")}',
                            '{task_config['component_id']}', '{task_config['component_name'].replace("'", "''")}',
                            '{task_config['category']}', {'NULL' if not notebook_path else f"'{notebook_path}'"},
                            '{json.dumps(task_config['config']).replace("'", "''")}',
                            '{json.dumps(task_config.get('thresholds', {})).replace("'", "''")}',
                            {task_order}, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
                print(f"DEBUG: Executing task insert query for task {task_key}")
                cursor.execute(insert_query)
                cursor.close()
                return task_id
        except Exception as e:
            print(f"Error creating DQ task: {str(e)}")
            return None
    
    @staticmethod
    def update_job_databricks_info(job_id: int, databricks_job_id: int, databricks_job_url: str) -> bool:
        """
        Update job with Databricks job ID and URL after creation
        
        Args:
            job_id: Internal job ID
            databricks_job_id: Databricks job ID
            databricks_job_url: URL to Databricks job
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                full_jobs_table = _full_table('dq_jobs')
                
                update_query = f"""
                    UPDATE {full_jobs_table}
                    SET databricks_job_id = {databricks_job_id},
                        databricks_job_url = '{databricks_job_url}',
                        status = 'deployed',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = {job_id}
                """
                cursor.execute(update_query)
                cursor.close()
                return True
        except Exception as e:
            print(f"Error updating job Databricks info: {str(e)}")
            return False

    @staticmethod
    def update_omd_fqn(job_id: int, omd_fqn: str) -> bool:
        """
        Persist the OpenMetadata FQN on a job row.

        Returns:
            True if successful, False otherwise
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                full_jobs_table = _full_table('dq_jobs')
                escaped_fqn = (omd_fqn or '').replace("'", "''")
                update_query = f"""
                    UPDATE {full_jobs_table}
                    SET omd_fqn = '{escaped_fqn}',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = {job_id}
                """
                cursor.execute(update_query)
                cursor.close()
                return True
        except Exception as e:
            print(f"Error updating omd_fqn for job {job_id}: {str(e)}")
            return False

    # ------------------------------------------------------------------
    # OMD execution tracking
    # ------------------------------------------------------------------

    @staticmethod
    def create_omd_execution(
        job_id: int,
        omd_fqn: str,
        databricks_job_id: str = "",
        databricks_run_id: str = "",
        run_url: str = "",
    ) -> Optional[int]:
        """Insert a new row in dq_omd_executions at submission time.

        Returns:
            The new row id (auto-generated by SERIAL), or None on failure.
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                table = _full_table('dq_omd_executions')
                escaped_fqn    = (omd_fqn or '').replace("'", "''")
                escaped_job_id = (databricks_job_id or '').replace("'", "''")
                escaped_run_id = (databricks_run_id or '').replace("'", "''")
                escaped_url    = (run_url or '').replace("'", "''")
                cursor.execute(f"""
                    INSERT INTO {table}
                        (job_id, databricks_job_id, databricks_run_id,
                         run_url, omd_fqn, status, pushed_at)
                    VALUES
                        ({job_id}, '{escaped_job_id}', '{escaped_run_id}',
                         '{escaped_url}', '{escaped_fqn}', 'submitted', CURRENT_TIMESTAMP)
                    RETURNING id
                """)
                row = cursor.fetchone()
                row_id = row[0] if row else None
                cursor.close()
                return row_id
        except Exception as e:
            _repo_logger.error(f"[OMD_EXEC] create_omd_execution failed: {e}")
            return None

    @staticmethod
    def update_omd_execution_status(
        exec_id: int,
        status: str,
        columns_pushed: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update status (and optionally columns_pushed / error_message) of an OMD execution row.

        Returns:
            True on success, False on failure.
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                table = _full_table('dq_omd_executions')
                parts = [f"status = '{status}'", "completed_at = CURRENT_TIMESTAMP"]
                if columns_pushed is not None:
                    parts.append(f"columns_pushed = {int(columns_pushed)}")
                if error_message is not None:
                    escaped_err = error_message.replace("'", "''")
                    parts.append(f"error_message = '{escaped_err}'")
                cursor.execute(f"UPDATE {table} SET {', '.join(parts)} WHERE id = {exec_id}")
                cursor.close()
                return True
        except Exception as e:
            _repo_logger.error(f"[OMD_EXEC] update_omd_execution_status failed: {e}")
            return False

    @staticmethod
    def get_omd_executions_by_job(job_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """Return recent OMD executions for a given DQ job, newest first.

        Returns:
            List of execution dicts.
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                table = _full_table('dq_omd_executions')
                cursor.execute(
                    f"SELECT * FROM {table} WHERE job_id = {int(job_id)} ORDER BY pushed_at DESC LIMIT {int(limit)}"
                )
                results = cursor.fetchall()
                columns = [d[0] for d in cursor.description] if cursor.description else []
                cursor.close()
                return [dict(zip(columns, row)) for row in results]
        except Exception as e:
            _repo_logger.error(f"[OMD_EXEC] get_omd_executions_by_job failed: {e}")
            return []

    @staticmethod
    def get_latest_omd_status_by_job(job_id: int) -> Optional[str]:
        """Return the latest `status` value from dq_omd_executions for a job_id."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                table = _full_table('dq_omd_executions')
                cursor.execute(f"SELECT status FROM {table} WHERE job_id = {int(job_id)} ORDER BY pushed_at DESC LIMIT 1")
                row = cursor.fetchone()
                cursor.close()
                if row and len(row) > 0:
                    return row[0]
                return None
        except Exception as e:
            _repo_logger.error(f"[OMD_EXEC] get_latest_omd_status_by_job failed: {e}")
            return None

    @staticmethod
    def create_execution(job_id: int, databricks_run_id, run_url: str,
                        triggered_by: str, trigger_type: str) -> Optional[int]:
        """
        Create a new execution record when job is triggered.

        Tries fresh connection first; falls back to pooled connection.
        Raises RuntimeError if both attempts fail so callers can surface the error.

        Returns:
            Execution ID (int) — raises RuntimeError on failure.
        """
        import logging as _logging
        _log = _logging.getLogger(__name__)

        full_executions_table = _full_table('dq_executions')
        execution_id = _generate_id()

        # Ensure BIGINT-safe integer for the run_id column
        try:
            run_id_int = int(databricks_run_id)
        except (ValueError, TypeError):
            run_id_int = databricks_run_id

        # Escape SQL-unsafe characters
        escaped_url = (run_url or '').replace("'", "''")
        escaped_triggered_by = (triggered_by or 'system').replace("'", "''")

        insert_query = f"""
            INSERT INTO {full_executions_table}
            (id, job_id, databricks_run_id, run_url, status, start_time,
             triggered_by, trigger_type, created_at)
            VALUES ({execution_id}, {job_id}, {run_id_int}, '{escaped_url}',
                    'running', CURRENT_TIMESTAMP, '{escaped_triggered_by}',
                    '{trigger_type}', CURRENT_TIMESTAMP)
        """

        last_err = None
        # Attempt 1: fresh connection
        try:
            with get_db_connection_fresh() as conn:
                cursor = conn.cursor()
                cursor.execute(insert_query)
                cursor.close()
                try:
                    conn.commit()
                except Exception:
                    pass  # auto-commit drivers don't expose commit()
            _log.info(f"[CREATE_EXECUTION] ✅ Execution {execution_id} created (fresh conn) for job {job_id}, run {run_id_int}")
            return execution_id
        except Exception as e:
            last_err = e
            _log.warning(f"[CREATE_EXECUTION] fresh-conn attempt failed: {e}; retrying with pooled connection")

        # Attempt 2: pooled connection
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(insert_query)
                cursor.close()
                try:
                    conn.commit()
                except Exception:
                    pass
            _log.info(f"[CREATE_EXECUTION] ✅ Execution {execution_id} created (pooled conn) for job {job_id}, run {run_id_int}")
            return execution_id
        except Exception as e:
            last_err = e
            _log.error(f"[CREATE_EXECUTION] ❌ Both attempts failed. Last error: {e}\nQuery: {insert_query}")
            raise RuntimeError(f"Failed to create execution record: {e}") from e
    
    @staticmethod
    def get_job_tasks(job_id: int) -> List[Dict[str, Any]]:
        """
        Get all tasks for a job
        
        Args:
            job_id: Job ID
            
        Returns:
            List of task dictionaries
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            full_table = _full_table('dq_tasks')
            
            cursor.execute(f"SELECT * FROM {full_table} WHERE job_id = {job_id} ORDER BY task_order")
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            cursor.close()
            
            return [dict(zip(columns, row)) for row in results]
    
    @staticmethod
    def get_job_executions(job_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get execution history for a job
        
        Args:
            job_id: Job ID
            limit: Maximum number of executions to return
            
        Returns:
            List of execution dictionaries
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            full_table = _full_table('dq_executions')
            
            cursor.execute(f"SELECT * FROM {full_table} WHERE job_id = {job_id} ORDER BY start_time DESC LIMIT {limit}")
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            cursor.close()
            
            return [dict(zip(columns, row)) for row in results]

    @staticmethod
    def get_running_executions(job_id: int) -> List[Dict[str, Any]]:
        """Return all executions with status='running' for a job (for reconciliation)."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            full_table = _full_table('dq_executions')
            cursor.execute(
                f"SELECT * FROM {full_table} WHERE job_id = {int(job_id)} AND status = 'running' ORDER BY start_time DESC"
            )
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            cursor.close()
            return [dict(zip(columns, row)) for row in results]

    @staticmethod
    def get_job_with_executions(job_id: int, limit: int = 20) -> tuple:
        """Fetch job metadata and its recent executions in a single connection.

        Each execution dict includes a ``dashboard_url`` field (None if not yet
        created) so the frontend needs zero additional API calls.

        Returns:
            (job_dict | None, list[execution_dict])
        """
        jobs_table  = _full_table('dq_jobs')
        execs_table = _full_table('dq_executions')
        dash_table  = _full_table('dq_dashboards')

        def _run_queries(conn):
            cursor = conn.cursor()
            # 1. job row
            cursor.execute(f"SELECT * FROM {jobs_table} WHERE id = {int(job_id)}")
            job_rows = cursor.fetchall()
            job_cols = [d[0] for d in cursor.description] if cursor.description else []
            job = dict(zip(job_cols, job_rows[0])) if job_rows else None
            if not job:
                cursor.close()
                return None, []
            # 2. executions + dashboard_url in one LEFT JOIN
            cursor.execute(f"""
                SELECT e.*, d.dashboard_url, d.dashboard_id
                FROM {execs_table} e
                LEFT JOIN (
                    SELECT execution_id, dashboard_url, dashboard_id,
                           ROW_NUMBER() OVER (PARTITION BY execution_id ORDER BY created_at DESC) AS rn
                    FROM {dash_table}
                ) d ON d.execution_id = e.id AND d.rn = 1
                WHERE e.job_id = {int(job_id)}
                ORDER BY e.start_time DESC
                LIMIT {int(limit)}
            """)
            exec_rows = cursor.fetchall()
            exec_cols = [d[0] for d in cursor.description] if cursor.description else []
            cursor.close()
            return job, [dict(zip(exec_cols, row)) for row in exec_rows]

        # First attempt with pooled connection; on failure retry with a fresh one.
        try:
            with get_db_connection() as conn:
                return _run_queries(conn)
        except Exception:
            with get_db_connection_fresh() as conn:
                return _run_queries(conn)

    @staticmethod
    def get_execution_results(execution_id: int) -> List[Dict[str, Any]]:
        """
        Get all task results for an execution
        
        Args:
            execution_id: Execution ID
            
        Returns:
            List of task result dictionaries
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            full_table = _full_table('dq_task_results')
            
            cursor.execute(f"SELECT * FROM {full_table} WHERE execution_id = {execution_id} ORDER BY start_time")
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            cursor.close()
            
            return [dict(zip(columns, row)) for row in results]
    
    @staticmethod
    def get_job_by_id(job_id: int) -> Optional[Dict[str, Any]]:
        """
        Get job by ID
        
        Args:
            job_id: Job ID
            
        Returns:
            Job dictionary or None
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            full_table = _full_table('dq_jobs')
            
            cursor.execute(f"SELECT * FROM {full_table} WHERE id = {job_id}")
            result = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            cursor.close()
            
            if result and len(result) > 0:
                return dict(zip(columns, result[0]))
            return None
    
    @staticmethod
    def delete_job(job_id: int) -> bool:
        """
        Delete a job and all its related records.
        Order matters due to FK constraints:
          dq_alerts, dq_task_results → dq_executions
          dq_executions, dq_tasks, dq_schedules, dq_notebooks, dq_dashboards → dq_jobs
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                job_id = int(job_id)

                # 1. Delete records that reference dq_executions
                exec_ids_query = f"SELECT id FROM {_full_table('dq_executions')} WHERE job_id = {job_id}"
                cursor.execute(exec_ids_query)
                exec_ids = [row[0] for row in cursor.fetchall()]

                if exec_ids:
                    ids_str = ','.join(str(i) for i in exec_ids)
                    cursor.execute(f"DELETE FROM {_full_table('dq_alerts')} WHERE execution_id IN ({ids_str})")
                    cursor.execute(f"DELETE FROM {_full_table('dq_task_results')} WHERE execution_id IN ({ids_str})")

                # 2. Delete records that reference dq_jobs directly
                cursor.execute(f"DELETE FROM {_full_table('dq_executions')} WHERE job_id = {job_id}")
                cursor.execute(f"DELETE FROM {_full_table('dq_tasks')} WHERE job_id = {job_id}")
                cursor.execute(f"DELETE FROM {_full_table('dq_schedules')} WHERE job_id = {job_id}")
                cursor.execute(f"DELETE FROM {_full_table('dq_notebooks')} WHERE job_id = {job_id}")
                cursor.execute(f"DELETE FROM {_full_table('dq_dashboards')} WHERE job_id = {job_id}")

                # 3. Finally delete the job itself
                cursor.execute(f"DELETE FROM {_full_table('dq_jobs')} WHERE id = {job_id}")
                cursor.close()
                return True
        except Exception as e:
            _repo_logger.error(f"Error deleting job {job_id}: {str(e)}", exc_info=True)
            return False
    
    @staticmethod
    def get_jobs_by_project(project_id: int) -> List[Dict[str, Any]]:
        """
        Get all jobs for a project
        
        Args:
            project_id: Project ID
        Returns:
            List of job dictionaries (ordered by created_at DESC)
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            full_table = _full_table('dq_jobs')
            query = f"SELECT * FROM {full_table} WHERE project_id = %s ORDER BY created_at DESC"
            cursor.execute(query, (project_id,))
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            cursor.close()
            jobs = []
            for row in results:
                jobs.append(dict(zip(columns, row)))
            return jobs
    
    @staticmethod
    def update_execution_status(run_id: str, status: str, error_message: Optional[str] = None) -> bool:
        """
        Update execution status from Databricks run status
        
        Args:
            run_id: Databricks run ID
            status: Execution status (pending, running, completed, failed)
            error_message: Error message if failed (optional)
            
        Returns:
            True if successful, False otherwise
        """
        _safe = lambda v: str(v).replace('\n', '_').replace('\r', '_') if v is not None else 'None'
        _repo_logger.info("[UPDATE_EXECUTION_STATUS] run_id=%s status=%s error_message=%s",
                          _safe(run_id), _safe(status), _safe(error_message))

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()

                # Cast to int to match the BIGINT column type (avoids silent 0-row UPDATE)
                try:
                    run_id_int = int(run_id)
                except (ValueError, TypeError):
                    run_id_int = run_id

                JobRepository._apply_execution_status(cursor, run_id_int, status, error_message)

                # 'completed' is our mapped status, 'SUCCESS' the Databricks one
                if status == 'completed' or (status or '').upper() == 'SUCCESS':
                    JobRepository._create_dashboard_for_run(cursor, run_id, run_id_int)

                cursor.close()
                return True
        except Exception as e:
            print(f"Error updating execution status: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    @staticmethod
    def _apply_execution_status(cursor, run_id, status: str, error_message: Optional[str]) -> None:
        """Update the status (and end time / error message) of the execution matching the Databricks run id."""
        assignments = ["status = %s"]
        params = [status]
        if status in ('completed', 'failed'):
            assignments.append("end_time = CURRENT_TIMESTAMP")
        if error_message:
            assignments.append("error_message = %s")
            params.append(error_message)
        params.append(run_id)

        cursor.execute(
            f"UPDATE {_full_table('dq_executions')} SET {', '.join(assignments)} WHERE databricks_run_id = %s",
            params
        )
        _repo_logger.info("[UPDATE_EXECUTION_STATUS] Status updated to: %s",
                          str(status).replace('\n', '_').replace('\r', '_'))

    @staticmethod
    def _create_dashboard_for_run(cursor, run_id, run_id_int) -> None:
        """Create the Lakeview dashboard of a successfully completed run (failures never propagate)."""
        _repo_logger.info("[UPDATE_EXECUTION] Job completed successfully (run %s), triggering dashboard creation",
                          str(run_id).replace('\n', '_').replace('\r', '_'))

        cursor.execute(
            f"""
            SELECT
                e.id as execution_id,
                j.id as job_id,
                j.job_name,
                p.project_name,
                p.config,
                e.triggered_by
            FROM {_full_table('dq_executions')} e
            JOIN {_full_table('dq_jobs')} j ON e.job_id = j.id
            JOIN {_full_table('dq_projects')} p ON j.project_id = p.id
            WHERE e.databricks_run_id = %s
            """,
            (run_id_int,)
        )
        result = cursor.fetchone()

        if not result:
            _repo_logger.error("[UPDATE_EXECUTION] No execution found for run_id: %s",
                               str(run_id).replace('\n', '_').replace('\r', '_'))
            cursor.execute(
                f"SELECT databricks_run_id, status, id FROM {_full_table('dq_executions')} ORDER BY id DESC LIMIT 5"
            )
            for recent in cursor.fetchall():
                _repo_logger.info(f"[UPDATE_EXECUTION] Recent execution: run_id={recent[0]}, status={recent[1]}, id={recent[2]}")
            return  # Don't fail the status update

        execution_id, job_id, job_name, project_name, config_json, triggered_by = result[:6]
        config = json.loads(config_json) if config_json else {}
        JobRepository._publish_dashboard(
            job_id=job_id,
            execution_id=execution_id,
            project_name=project_name,
            job_name=job_name,
            owner_email=triggered_by or '',
            catalog=config.get('catalog') or os.getenv('UC_CATALOG', 'dbr_uat01_gdm'),
            results_schema=config.get('results_schema') or os.getenv('UC_RESULTS_SCHEMA', 'db_gdm_dq_results'),
        )

    @staticmethod
    def _publish_dashboard(job_id, execution_id, project_name, job_name, owner_email, catalog, results_schema) -> None:
        """Create the dashboard and record it; failures are logged only (not persisted) and never propagate."""
        try:
            from services.databricks_dashboard_service import DatabricksDashboardService
            dashboard_result = DatabricksDashboardService().create_dq_dashboard(
                job_id=job_id,
                project_name=project_name,
                job_name=job_name,
                execution_id=execution_id,
                catalog=catalog,
                results_schema=results_schema,
                owner_email=owner_email
            )

            if dashboard_result.get('status') != 'success':
                _repo_logger.warning(
                    f"[UPDATE_EXECUTION] Dashboard creation failed: {dashboard_result.get('message', 'Unknown error')}"
                )
                return

            _repo_logger.info(f"[UPDATE_EXECUTION] Dashboard created: {dashboard_result.get('dashboard_url')}")
            JobRepository.save_dashboard_info(
                job_id=job_id,
                execution_id=execution_id,
                dashboard_id=dashboard_result.get('dashboard_id'),
                dashboard_name=dashboard_result.get('dashboard_name'),
                dashboard_url=dashboard_result.get('dashboard_url'),
                catalog=catalog,
                results_schema=results_schema
            )
        except Exception as dashboard_error:
            _repo_logger.error(
                f"[UPDATE_EXECUTION] Dashboard creation error (non-fatal) "
                f"type={type(dashboard_error).__name__} error={dashboard_error}",
                exc_info=True
            )
    
    @staticmethod
    def save_dashboard_info(
        job_id: int,
        execution_id: int,
        dashboard_id: Optional[str],
        dashboard_name: Optional[str],
        dashboard_url: Optional[str],
        catalog: str,
        results_schema: str,
        status: str = 'success',
        error_message: Optional[str] = None
    ) -> bool:
        """
        Save dashboard information to database
        
        Args:
            job_id: Job ID
            execution_id: Execution ID
            dashboard_id: Databricks dashboard ID (REQUIRED - must not be None)
            dashboard_name: Dashboard name
            dashboard_url: Dashboard URL (REQUIRED - must not be None)
            catalog: Databricks catalog
            results_schema: Results schema
            status: Creation status (should be 'success' for valid saves)
            error_message: Error message if any
            
        Returns:
            True if successful, False otherwise
        """
        print(f"[SAVE_DASHBOARD] Called with: dashboard_id={dashboard_id}, dashboard_url={dashboard_url}, status={status}")
        
        # Validate required fields
        if not dashboard_id or not dashboard_url:
            print(f"[SAVE_DASHBOARD] ❌ Validation failed: dashboard_id and dashboard_url are required (NOT NULL)")
            print(f"[SAVE_DASHBOARD]   dashboard_id: {dashboard_id}")
            print(f"[SAVE_DASHBOARD]   dashboard_url: {dashboard_url}")
            print(f"[SAVE_DASHBOARD]   Skipping database save to avoid constraint violation")
            return False
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                full_dashboards_table = _full_table('dq_dashboards')
                
                dashboard_db_id = _generate_id()
                
                # Escape strings for SQL
                def escape_sql(s):
                    if s is None:
                        return 'NULL'
                    return f"'{s.replace(chr(39), chr(39)+chr(39))}'"
                
                insert_query = f"""
                    INSERT INTO {full_dashboards_table}
                    (id, job_id, execution_id, dashboard_id, dashboard_name, dashboard_url,
                     catalog, results_schema, status, error_message, created_at, updated_at)
                    VALUES (
                        {dashboard_db_id},
                        {job_id},
                        {execution_id if execution_id else 'NULL'},
                        {escape_sql(dashboard_id)},
                        {escape_sql(dashboard_name)},
                        {escape_sql(dashboard_url)},
                        {escape_sql(catalog)},
                        {escape_sql(results_schema)},
                        '{status}',
                        {escape_sql(error_message)},
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    )
                """
                cursor.execute(insert_query)
                cursor.close()
                
                print(f"[SAVE_DASHBOARD] ✅ Dashboard info saved: ID={dashboard_db_id}, job_id={job_id}, execution_id={execution_id}")
                return True
        except Exception as e:
            print(f"[SAVE_DASHBOARD] ❌ Error saving dashboard info: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    @staticmethod
    def get_dashboard_for_execution(execution_id: int) -> Optional[Dict[str, Any]]:
        """
        Get dashboard information for a specific execution
        
        Args:
            execution_id: Execution ID
            
        Returns:
            Dashboard dictionary or None
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                full_dashboards_table = _full_table('dq_dashboards')
                
                query = f"""
                    SELECT id, job_id, execution_id, dashboard_id, dashboard_name,
                           dashboard_url, catalog, results_schema, status,
                           error_message, created_at, updated_at
                    FROM {full_dashboards_table}
                    WHERE execution_id = {execution_id}
                    ORDER BY created_at DESC
                    LIMIT 1
                """
                cursor.execute(query)
                result = cursor.fetchone()
                cursor.close()
                
                if result:
                    return {
                        'id': result[0],
                        'job_id': result[1],
                        'execution_id': result[2],
                        'dashboard_id': result[3],
                        'dashboard_name': result[4],
                        'dashboard_url': result[5],
                        'catalog': result[6],
                        'results_schema': result[7],
                        'status': result[8],
                        'error_message': result[9],
                        'created_at': result[10],
                        'updated_at': result[11]
                    }
                return None
        except Exception as e:
            print(f"[GET_DASHBOARD] Error getting dashboard for execution {execution_id}: {str(e)}")
            return None
    
    @staticmethod
    def get_dashboards_for_job(job_id: int) -> List[Dict[str, Any]]:
        """
        Get all dashboards for a job
        
        Args:
            job_id: Job ID
            
        Returns:
            List of dashboard dictionaries
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                full_dashboards_table = _full_table('dq_dashboards')
                
                query = f"""
                    SELECT id, job_id, execution_id, dashboard_id, dashboard_name,
                           dashboard_url, catalog, results_schema, status,
                           error_message, created_at, updated_at
                    FROM {full_dashboards_table}
                    WHERE job_id = {job_id}
                    ORDER BY created_at DESC
                """
                cursor.execute(query)
                results = cursor.fetchall()
                cursor.close()
                
                dashboards = []
                for result in results:
                    dashboards.append({
                        'id': result[0],
                        'job_id': result[1],
                        'execution_id': result[2],
                        'dashboard_id': result[3],
                        'dashboard_name': result[4],
                        'dashboard_url': result[5],
                        'catalog': result[6],
                        'results_schema': result[7],
                        'status': result[8],
                        'error_message': result[9],
                        'created_at': result[10],
                        'updated_at': result[11]
                    })
                return dashboards
        except Exception as e:
            print(f"[GET_DASHBOARDS] Error getting dashboards for job {job_id}: {str(e)}")
            return []
    
    @staticmethod
    def update_job_schedule(job_id: int, schedule_config: Dict[str, Any]) -> bool:
        """
        Create or update job schedule configuration
        
        Args:
            job_id: Job ID
            schedule_config: Schedule configuration dictionary
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                full_schedules_table = _full_table('dq_schedules')
                
                # Check if schedule already exists
                cursor.execute(f"SELECT id FROM {full_schedules_table} WHERE job_id = {job_id}")
                existing = cursor.fetchone()
                
                cron_expression = schedule_config.get('cron_expression', '0 0 * * *')
                timezone = schedule_config.get('timezone', 'UTC')
                schedule_type = schedule_config.get('schedule_type', 'custom')
                is_active = schedule_config.get('enabled', True)
                
                if existing:
                    # Update existing schedule
                    schedule_id = existing[0]
                    update_query = f"""
                        UPDATE {full_schedules_table}
                        SET cron_expression = '{cron_expression}',
                            timezone = '{timezone}',
                            schedule_type = '{schedule_type}',
                            is_active = {is_active},
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = {schedule_id}
                    """
                    cursor.execute(update_query)
                else:
                    # Create new schedule
                    schedule_id = _generate_id()
                    insert_query = f"""
                        INSERT INTO {full_schedules_table}
                        (id, job_id, schedule_type, cron_expression, timezone, is_active, 
                         created_at, updated_at)
                        VALUES ({schedule_id}, {job_id}, '{schedule_type}', '{cron_expression}',
                                '{timezone}', {is_active}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                    cursor.execute(insert_query)
                
                # Also update schedule columns in dq_jobs table for consistency
                full_jobs_table = _full_table('dq_jobs')
                update_jobs_query = f"""
                    UPDATE {full_jobs_table}
                    SET schedule_cron = '{cron_expression}',
                        schedule_timezone = '{timezone}',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = {job_id}
                """
                cursor.execute(update_jobs_query)
                
                cursor.close()
                return True
        except Exception as e:
            print(f"Error updating job schedule: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    @staticmethod
    def get_job_schedule(job_id: int) -> Optional[Dict[str, Any]]:
        """
        Get schedule configuration for a job
        
        Args:
            job_id: Job ID
            
        Returns:
            Schedule dictionary or None
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                full_schedules_table = _full_table('dq_schedules')
                
                cursor.execute(f"SELECT * FROM {full_schedules_table} WHERE job_id = {job_id}")
                result = cursor.fetchone()
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                cursor.close()
                
                if result:
                    return dict(zip(columns, result))
                return None
        except Exception as e:
            print(f"Error getting job schedule: {str(e)}")
            return None
    
    @staticmethod
    def delete_job_schedule(job_id: int) -> bool:
        """
        Delete schedule for a job
        
        Args:
            job_id: Job ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                full_schedules_table = _full_table('dq_schedules')
                
                cursor.execute(f"DELETE FROM {full_schedules_table} WHERE job_id = {job_id}")
                cursor.close()
                return True
        except Exception as e:
            print(f"Error deleting job schedule: {str(e)}")
            return False
    
    @staticmethod
    def _prepare_source_config(source_config):
        """Normalize a source_config (dict or JSON string) so the fields of the other source type are reset."""
        if isinstance(source_config, str):
            try:
                config_obj = json.loads(source_config)
            except Exception:
                return source_config
        else:
            config_obj = source_config

        if not isinstance(config_obj, dict) or not config_obj:
            return source_config

        source_type = config_obj.get("source_type")
        if source_type == "unity_catalog":
            config_obj["dbfs_path"] = ""
        elif source_type == "csv":
            config_obj.update({"catalog": "", "schema": "", "table": ""})
        return config_obj

    @staticmethod
    def _build_update_assignments(updates: Dict[str, Any]) -> tuple:
        """SET clauses and their parameters for an UPDATE; field names must be plain column identifiers."""
        assignments = []
        params = []
        for field, value in updates.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", field):
                raise ValueError(f"Invalid column name: {field}")
            if value is None:
                assignments.append(f"{field} = NULL")
                continue
            assignments.append(f"{field} = %s")
            params.append(json.dumps(value) if isinstance(value, (dict, list)) else value)
        return assignments, params

    @staticmethod
    def update_job(job_id: int, updates: Dict[str, Any]) -> bool:
        """
        Update job fields (generic update method for 3-layer architecture)
        
        Args:
            job_id: Job ID
            updates: Dictionary of field names and values to update
                    Supports: job_name, job_description, step, source_type, 
                             source_config, quality_config, schedule_cron, 
                             schedule_timezone, deployed_by, run_count, is_primary, status
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not updates:
                return True  # Nothing to update

            if "source_config" in updates:
                updates["source_config"] = JobRepository._prepare_source_config(updates["source_config"])

            with get_db_connection() as conn:
                cursor = conn.cursor()
                assignments, params = JobRepository._build_update_assignments(updates)

                # Always update updated_at
                assignments.append("updated_at = CURRENT_TIMESTAMP")
                params.append(job_id)

                cursor.execute(
                    f"UPDATE {_full_table('dq_jobs')} SET {', '.join(assignments)} WHERE id = %s",
                    params
                )
                cursor.close()
                return True
        except Exception as e:
            print(f"Error updating job: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
