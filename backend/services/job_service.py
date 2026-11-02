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
Job Service - Business logic for DQ job operations
"""
from typing import Dict, Any, List, Optional, Tuple
import logging
import os
import re
import io
import csv
from datetime import datetime, timezone
from database.repositories import JobRepository
from services.databricks_service import DatabricksService
from services.databricks_deployment_service import DatabricksDeploymentService
from config.settings import Settings

logger = logging.getLogger(__name__)

JOB_NOT_FOUND = "Job not found"
PROJECT_NOT_FOUND = "Project not found"
DEFAULT_OMD_PUSH_NOTEBOOK_PATH = "/Workspace/Shared/notebooks/push_dq_to_omd"


class JobService:
    """Service for job-related business logic"""
    
    def __init__(self):
        self.repository = JobRepository()
        self.databricks_service = DatabricksService()
        self.deployment_service = DatabricksDeploymentService()
    
    def deploy_dq_job(self, project_id: int, project_config: Dict[str, Any],
                     enabled_components: List[Dict[str, Any]],
                     deployment_config: Dict[str, Any],
                     user_email: str = None):
        """
        Deploy complete DQ job with notebooks and tasks
        Generator that yields status updates from deployment service
        
        Args:
            project_id: Project ID
            project_config: Project configuration (source, columns, etc.)
            enabled_components: List of enabled DQ components
            deployment_config: Job deployment configuration
            user_email: User's email to set as job owner (optional)
            
        Yields:
            Dictionary with status updates from deployment
        """
        try:
            logger.info(f"Deploying job for project {project_id}, user: {user_email}")
            logger.info(f"Deployment config: {deployment_config}")
            
            # Track final result for database insertion
            final_result = None
            
            # Deploy to Databricks FIRST (creates notebooks and job)
            # This is now a generator, so we yield each update
            for update in self.deployment_service.deploy_dq_job(
                project_id,
                project_config,
                enabled_components,
                deployment_config,
                user_email=user_email
            ):
                logger.info(f"[DEPLOY] Received update: step={update.get('step')}, status={update.get('status')}")
                
                # Pass through all updates
                yield update
                
                # Capture final result for database insertion
                if update.get('step') == 'complete' and update.get('status') == 'success':
                    logger.info(f"[DEPLOY] Captured final result with job_id={update.get('job_id')}")
                    final_result = update
                
                # Stop if there's an error
                if update.get('status') == 'error':
                    logger.error(f"Deployment failed: {update.get('message')}")
                    return
            
            # If we have a final result, create or update database record
            if final_result and final_result.get('job_id'):
                yield self._save_job_record(project_id, deployment_config, final_result, user_email)
            else:
                logger.error(f"[DEPLOY] ❌ Deployment completed but no final result received. final_result={final_result}")
                yield {
                    'step': 'database',
                    'status': 'error',
                    'message': 'Deployment completed but job information is missing'
                }
            
        except Exception as e:
            logger.error(f"ERROR in deploy_dq_job service: {str(e)}", exc_info=True)
            yield {
                'step': 'service_error',
                'status': 'error',
                'message': f'Service error: {str(e)}'
            }
    
    def _save_job_record(self, project_id: int, deployment_config: Dict[str, Any],
                         final_result: Dict[str, Any], user_email: str = None) -> Dict[str, Any]:
        """Persist the freshly deployed Databricks job and return the resulting status update."""
        databricks_job_id = final_result['job_id']
        job_url = final_result.get('job_url', '')
        existing_job_id = deployment_config.get('existing_job_id')
        # Store the raw user-provided name, not the "project_job" Databricks name,
        # otherwise every redeploy would add another project prefix.
        raw_job_name = deployment_config.get('job_name', f'job_{project_id}')
        workspace_path = final_result.get('workspace_path', '')
        deployed_by = user_email or 'unknown'

        if existing_job_id:
            logger.info(f"[DB] Updating existing job {existing_job_id} with Databricks info: job_id={databricks_job_id}")
            job_updates = {
                'job_name': raw_job_name,
                'job_description': deployment_config.get('job_description', ''),
                'databricks_job_id': databricks_job_id,
                'databricks_job_url': job_url,
                'workspace_path': workspace_path,
                'deployed_by': deployed_by,
                'status': 'deployed'
            }
            if not self.repository.update_job(existing_job_id, job_updates):
                logger.error(f"[DB] ❌ Failed to update job {existing_job_id}")
                return {'step': 'database', 'status': 'error', 'message': f'Failed to update job {existing_job_id}'}
            logger.info(f"[DB] ✅ Job {existing_job_id} updated successfully")
            return {
                'step': 'database',
                'status': 'success',
                'message': f'Job {existing_job_id} updated with new deployment',
                'db_job_id': existing_job_id,
                'databricks_job_id': databricks_job_id,
                'job_url': job_url
            }

        logger.info(f"[DB] Creating database record for Databricks job: ID={databricks_job_id}, URL={job_url}")
        job_config = {
            'job_name': raw_job_name,
            'description': deployment_config.get('job_description', ''),
            'notification_email': deployment_config.get('notification_email', ''),
            'failure_action': deployment_config.get('failure_action', 'Alert Only'),
            'retry_attempts': deployment_config.get('retry_attempts', 0),
            'priority': deployment_config.get('priority', 'Medium'),
            'workspace_path': workspace_path,
            'deployed_by': deployed_by
        }
        db_job_id = self.repository.create_job(project_id, job_config)
        if not db_job_id:
            # Databricks job exists but the DB record failed - this is critical
            logger.error(f"[DB] ❌ Failed to create database record for Databricks job {databricks_job_id}")
            return {
                'step': 'database',
                'status': 'error',
                'message': f'Failed to create database record (Databricks job {databricks_job_id} created successfully)'
            }

        logger.info(f"[DB] ✅ Database job record created with ID: {db_job_id}")
        if not self.repository.update_job_databricks_info(db_job_id, databricks_job_id, job_url):
            logger.error(f"[DB] ❌ Failed to update job {db_job_id} with Databricks info")
            return {
                'step': 'database',
                'status': 'warning',
                'message': 'Job created but failed to update Databricks info'
            }
        logger.info(f"[DB] ✅ Job {db_job_id} updated with Databricks info successfully")
        return {
            'step': 'database',
            'status': 'success',
            'message': f'Job record created in database with ID {db_job_id}',
            'db_job_id': db_job_id,
            'databricks_job_id': databricks_job_id,
            'job_url': job_url
        }

    def deploy_job(self, project_id: int, deployment_config: Dict[str, Any], 
                   quality_controls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Deploy data quality job to Databricks with tasks for each check
        
        Args:
            project_id: Project ID
            deployment_config: Deployment configuration
            quality_controls: List of quality control configurations
            
        Returns:
            Dictionary with status and job information
        """
        try:
            # Create job record in database
            job_config = {
                'job_name': deployment_config.get('job_name'),
                'description': deployment_config.get('job_description', ''),
                'notification_email': deployment_config.get('notification_email', ''),
                'failure_action': deployment_config.get('failure_action', 'Alert Only'),
                'retry_attempts': deployment_config.get('retry_attempts', 0),
                'priority': deployment_config.get('priority', 'Medium')
            }
            
            job_id = self.repository.create_job(project_id, job_config)
            
            if not job_id:
                return {
                    "status": "error",
                    "message": "Failed to create job record"
                }
            
            # Create task records for each quality check
            tasks_config = []
            for idx, control in enumerate(quality_controls):
                task_config = {
                    'component_id': control['component_id'],
                    'task_name': control['component_name'],
                    'component_name': control['component_name'],
                    'category': control['category'],
                    'config': control['config'],
                    'thresholds': control.get('thresholds', {}),
                    'retry_attempts': job_config['retry_attempts']
                }
                
                task_id = self.repository.create_task(job_id, task_config, idx)
                if task_id:
                    tasks_config.append(task_config)
            
            # Create Databricks job with tasks (one task per check)
            databricks_result = self.databricks_service.create_job(job_config, tasks_config)
            
            if databricks_result.get('status') != 'success':
                return databricks_result
            
            # Update job with Databricks info
            self.repository.update_job_databricks_info(
                job_id,
                databricks_result['job_id'],
                databricks_result.get('job_url', '')
            )
            
            return {
                "status": "success",
                "job_id": job_id,
                "databricks_job_id": databricks_result['job_id'],
                "job_url": databricks_result.get('job_url', ''),
                "tasks_count": len(tasks_config),
                "message": f"Job deployed successfully with {len(tasks_config)} quality checks"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Deployment failed: {str(e)}"
            }
    
    def run_job(self, job_id: int, triggered_by: str = "system", 
                parameters: Dict[str, str] = None) -> Dict[str, Any]:
        """
        Execute a deployed data quality job
        
        Args:
            job_id: Job ID
            triggered_by: User who triggered the run
            parameters: Optional parameters for the job
            
        Returns:
            Dictionary with status and execution information
        """
        try:
            logger.info(f"[RUN] Attempting to run job {job_id}, triggered by {triggered_by}")
            
            # Get job info from database
            job = self.repository.get_job_by_id(job_id)
            
            if not job:
                logger.error(f"[RUN] ❌ Job {job_id} not found in database")
                return {
                    "status": "error",
                    "message": JOB_NOT_FOUND
                }
            
            logger.info(f"[RUN] ✅ Found job in database: {job.get('job_name')}")
            
            databricks_job_id = job.get('databricks_job_id')
            
            if not databricks_job_id:
                return {
                    "status": "error",
                    "message": "Job not yet deployed to Databricks"
                }
            
            # Trigger job run in Databricks
            run_result = self.databricks_service.run_job(databricks_job_id, parameters)
            
            if run_result.get('status') != 'success':
                return run_result
            
            # Create execution record
            try:
                execution_id = self.repository.create_execution(
                    job_id,
                    run_result['run_id'],
                    run_result.get('run_url', ''),
                    triggered_by,
                    'manual'
                )
            except Exception as exec_err:
                # Surface the error — without an execution record, status and
                # history will be permanently empty for this run.
                logger.error(f"[RUN] ❌ Failed to create execution record for run {run_result['run_id']}: {exec_err}")
                return {
                    "status": "error",
                    "message": f"Databricks job started (run {run_result['run_id']}) but failed to save execution record: {exec_err}. Check backend logs."
                }

            return {
                "status": "success",
                "execution_id": execution_id,
                "run_id": run_result['run_id'],
                "run_url": run_result.get('run_url', ''),
                "message": "Job execution started"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Execution failed: {str(e)}"
            }
    
    def get_job_status(self, job_id: int) -> Dict[str, Any]:
        """
        Get status of all executions for a job
        
        Args:
            job_id: Job ID
            
        Returns:
            Dictionary with status and execution information
        """
        try:
            executions = self.repository.get_job_executions(job_id, limit=10)
            tasks = self.repository.get_job_tasks(job_id)
            
            return {
                "status": "success",
                "job_id": job_id,
                "tasks_count": len(tasks),
                "recent_executions": executions,
                "total_executions": len(executions)
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to get job status: {str(e)}"
            }
    
    def get_execution_results(self, execution_id: int) -> Dict[str, Any]:
        """
        Get detailed results for a specific execution
        
        Args:
            execution_id: Execution ID
            
        Returns:
            Dictionary with status and execution results
        """
        try:
            results = self.repository.get_execution_results(execution_id)
            
            return {
                "status": "success",
                "execution_id": execution_id,
                "results": results,
                "tasks_count": len(results)
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to get execution results: {str(e)}"
            }
    
    def get_run_status_live(self, job_id: int, run_id: str) -> Dict[str, Any]:
        """
        Get live status from Databricks for a specific run
        
        Args:
            job_id: Job ID (for validation)
            run_id: Databricks run ID
            
        Returns:
            Dictionary with live run status from Databricks
        """
        try:
            logger.info("Getting live status for job %s, run %s",
                        str(job_id).replace('\n', '_').replace('\r', '_'),
                        str(run_id).replace('\n', '_').replace('\r', '_'))
            
            # Get job to validate it exists
            job = self.repository.get_job_by_id(job_id)
            if not job:
                return {
                    "status": "error",
                    "message": JOB_NOT_FOUND
                }
            
            # Get live status from Databricks
            status_result = self.databricks_service.get_run_status(run_id)
            
            if status_result.get('status') == 'error':
                return status_result
            
            # Always update execution status in DB (pending, running, completed, failed)
            run_status = status_result.get('status')
            if run_status in ['pending', 'running', 'completed', 'failed']:
                # For failed runs, try to get error message
                error_msg = None
                if run_status == 'failed':
                    error_msg = status_result.get('state_message', 'Job execution failed')
                
                self.repository.update_execution_status(
                    run_id,
                    run_status,
                    error_msg
                )
            
            return {
                "status": "success",
                "run_status": status_result.get('status'),
                "databricks_state": status_result.get('databricks_state'),
                "result_state": status_result.get('result_state'),
                "start_time": status_result.get('start_time'),
                "end_time": status_result.get('end_time'),
                "tasks": status_result.get('tasks', [])
            }
        except Exception as e:
            logger.error(f"Failed to get live run status: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Failed to get run status: {str(e)}"
            }
    
    def get_run_output(self, job_id: int, run_id: str) -> Dict[str, Any]:
        """
        Get output and results from a completed run
        
        Args:
            job_id: Job ID (for validation)
            run_id: Databricks run ID
            
        Returns:
            Dictionary with run output and results
        """
        try:
            logger.info(f"Getting output for job {job_id}, run {run_id}")
            
            # Get job to validate it exists
            job = self.repository.get_job_by_id(job_id)
            if not job:
                return {
                    "status": "error",
                    "message": JOB_NOT_FOUND
                }
            
            # Get output from Databricks
            output_result = self.databricks_service.get_run_output(run_id)
            
            if output_result.get('status') == 'error':
                return output_result
            
            return {
                "status": "success",
                "run_id": run_id,
                "results": output_result
            }
        except Exception as e:
            logger.error(f"Failed to get run output: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Failed to get run output: {str(e)}"
            }
    
    def sync_running_executions(self, job_id: int) -> None:
        """
        Reconcile stale 'running' executions by checking their actual status in Databricks.
        Called from get_execution_history so any run whose frontend polling was interrupted
        gets its status corrected automatically on the next history page load.
        Only checks executions that have been running for more than 5 minutes to avoid
        adding latency for genuinely active runs still being polled by the frontend.
        """
        try:
            now = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC, like the stored timestamps
            for exec_row in self.repository.get_running_executions(job_id) or []:
                run_id = str(exec_row.get('databricks_run_id') or '')
                if not run_id or run_id == 'None':
                    continue
                # Skip very recent runs — the frontend is still actively polling them
                if self._started_within_seconds(exec_row.get('start_time'), now, 300):
                    continue
                self._reconcile_execution(exec_row, run_id)
        except Exception as e:
            logger.warning(f"[SYNC] sync_running_executions failed for job {job_id}: {e}")

    @staticmethod
    def _started_within_seconds(start_time, now: datetime, seconds: int) -> bool:
        """True if the run started less than `seconds` ago; unparsable times count as not recent."""
        if not start_time:
            return False
        try:
            if isinstance(start_time, str):
                start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00')).replace(tzinfo=None)
            else:
                start_dt = start_time
            return (now - start_dt).total_seconds() < seconds
        except Exception:
            return False

    def _reconcile_execution(self, exec_row: Dict[str, Any], run_id: str) -> None:
        """Align one stale 'running' execution with its actual Databricks status."""
        try:
            status_result = self.databricks_service.get_run_status(run_id)
            actual_status = status_result.get('status')
            if actual_status in ('completed', 'failed'):
                error_msg = status_result.get('state_message') if actual_status == 'failed' else None
                self.repository.update_execution_status(run_id, actual_status, error_msg)
                logger.info(f"[SYNC] ✅ Reconciled execution {exec_row.get('id')} run {run_id}: running → {actual_status}")
        except Exception as e:
            logger.warning(f"[SYNC] Could not reconcile execution {exec_row.get('id')} run {run_id}: {e}")

    def get_execution_history(self, job_id: int, limit: int = 20) -> Dict[str, Any]:
        """
        Get execution history for a job
        
        Args:
            job_id: Job ID
            limit: Maximum number of executions to return
            
        Returns:
            Dictionary with execution history
        """
        try:
            logger.info(f"[HISTORY] Getting execution history for job {job_id}, limit {limit}")

            # Silently fix any stale 'running' executions before returning history
            self.sync_running_executions(job_id)

            # Single DB round-trip: fetch job + executions together to avoid the
            # two-query latency that caused the frontend 10s timeout to fire.
            job, executions = self.repository.get_job_with_executions(job_id, limit=limit)

            if not job:
                logger.error(f"[HISTORY] ❌ Job {job_id} not found in database")
                return {
                    "status": "error",
                    "message": JOB_NOT_FOUND,
                    "executions": []
                }

            logger.info(f"[HISTORY] ✅ Found job: {job.get('job_name')}, {len(executions)} execution(s)")
            for exec in executions:
                logger.info(f"[HISTORY] Execution ID: {exec.get('id')}, Status: {exec.get('status')}, Run ID: {exec.get('databricks_run_id')}")

            return {
                "status": "success",
                "job_id": job_id,
                "job_name": job.get('job_name'),
                "databricks_job_id": job.get('databricks_job_id'),
                "job_url": job.get('databricks_job_url'),
                "executions": executions,
                "total_executions": len(executions)
            }
        except Exception as e:
            logger.error(f"Failed to get execution history: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Failed to get execution history: {str(e)}",
                "executions": []
            }
    
    def get_execution_dashboard(self, execution_id: int) -> Dict[str, Any]:
        """
        Get dashboard information for a specific execution
        
        Args:
            execution_id: Execution ID
            
        Returns:
            Dictionary with dashboard info
        """
        try:
            logger.info(f"[GET_DASHBOARD] Getting dashboard for execution {execution_id}")
            
            dashboard = self.repository.get_dashboard_for_execution(execution_id)
            
            if dashboard:
                logger.info(f"[GET_DASHBOARD] ✅ Found dashboard: {dashboard.get('dashboard_url')}")
                return {
                    "status": "success",
                    "dashboard": dashboard
                }
            else:
                logger.info(f"[GET_DASHBOARD] ⚠️ No dashboard found for execution {execution_id}")
                return {
                    "status": "error",
                    "message": "Dashboard not found"
                }
        except Exception as e:
            logger.error(f"[GET_DASHBOARD] Failed to get dashboard: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Failed to get dashboard: {str(e)}"
            }
    
    def get_job_dashboards(self, job_id: int) -> Dict[str, Any]:
        """
        Get all dashboards for a job
        
        Args:
            job_id: Job ID
            
        Returns:
            Dictionary with list of dashboards
        """
        try:
            logger.info(f"[GET_DASHBOARDS] Getting dashboards for job {job_id}")
            
            # Verify job exists
            job = self.repository.get_job_by_id(job_id)
            if not job:
                return {
                    "status": "error",
                    "message": JOB_NOT_FOUND
                }
            
            dashboards = self.repository.get_dashboards_for_job(job_id)
            logger.info(f"[GET_DASHBOARDS] ✅ Found {len(dashboards)} dashboards")
            
            return {
                "status": "success",
                "dashboards": dashboards,
                "count": len(dashboards)
            }
        except Exception as e:
            logger.error(f"[GET_DASHBOARDS] Failed to get dashboards: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Failed to get dashboards: {str(e)}"
            }
    
    def schedule_job(self, job_id: int, schedule_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Configure schedule for a Databricks job
        
        Args:
            job_id: Job ID
            schedule_config: Schedule configuration (cron, timezone, etc.)
            
        Returns:
            Dictionary with status
        """
        try:
            logger.info("Scheduling job %s", str(job_id).replace('\n', '_').replace('\r', '_'))
            
            # Get job info from database
            job = self.repository.get_job_by_id(job_id)
            if not job:
                return {
                    "status": "error",
                    "message": JOB_NOT_FOUND
                }
            
            databricks_job_id = job.get('databricks_job_id')
            if not databricks_job_id:
                return {
                    "status": "error",
                    "message": "Job not yet deployed to Databricks"
                }
            
            # Convert schedule config to Databricks format
            cron_expression = self._build_cron_expression(schedule_config)
            timezone = schedule_config.get('timezone', 'UTC')
            
            logger.info("Cron expression: %s, timezone: %s",
                        str(cron_expression).replace('\n', '_').replace('\r', '_'),
                        str(timezone).replace('\n', '_').replace('\r', '_'))
            
            # Update job schedule in Databricks
            databricks_result = self.databricks_service.update_job_schedule(
                str(databricks_job_id),
                cron_expression,
                timezone,
                pause_status='UNPAUSED'
            )
            
            if databricks_result.get('status') != 'success':
                logger.error(f"Failed to update Databricks schedule: {databricks_result.get('message')}")
                return {
                    "status": "error",
                    "message": f"Failed to update Databricks schedule: {databricks_result.get('message')}"
                }
            
            logger.info("Databricks schedule updated successfully")
            
            # Update schedule in database
            self.repository.update_job_schedule(job_id, {
                'cron_expression': cron_expression,
                'timezone': timezone,
                'schedule_type': schedule_config.get('schedule_type'),
                'enabled': True
            })
            
            logger.info("Database schedule updated successfully")
            
            return {
                "status": "success",
                "job_id": job_id,
                "databricks_job_id": databricks_job_id,
                "cron_expression": cron_expression,
                "timezone": timezone,
                "message": "Schedule configured successfully in Databricks and database"
            }
        except Exception as e:
            logger.error(f"Failed to schedule job: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Failed to schedule job: {str(e)}"
            }
    
    def _parse_cron_expression(self, cron_expression: str) -> Dict[str, Any]:
        """
        Parse Quartz cron expression to extract schedule details (reverse engineering)
        
        Quartz Cron Format: second minute hour day month dayofweek year
        
        Args:
            cron_expression: Quartz cron expression (7 fields)
            
        Returns:
            Dictionary with schedule_type, execution_time, execution_day (if applicable)
        """
        try:
            if not cron_expression or cron_expression.strip() == '':
                return {'schedule_type': 'manual', 'execution_time': None}

            parts = cron_expression.strip().split()

            # Handle both Unix (5 fields) and Quartz (7 fields) formats
            if len(parts) == 5:
                # Unix format: minute hour day month dayofweek
                minute, hour, day, _month, dayofweek = parts
            elif len(parts) == 7:
                # Quartz format: second minute hour day month dayofweek year
                _second, minute, hour, day, _month, dayofweek, _year = parts
            else:
                return {'schedule_type': 'custom', 'execution_time': None, 'cron_expression': cron_expression}

            execution_time = self._cron_execution_time(hour, minute)
            any_day = day in ('*', '?')
            any_weekday = dayofweek in ('*', '?')

            if any_day and any_weekday:
                return {'schedule_type': 'daily', 'execution_time': execution_time}

            if any_day:
                # Quartz: 1=Sunday, 2=Monday, ..., 7=Saturday
                day_mapping = {
                    '1': 'Sunday', '2': 'Monday', '3': 'Tuesday', '4': 'Wednesday',
                    '5': 'Thursday', '6': 'Friday', '7': 'Saturday'
                }
                return {
                    'schedule_type': 'weekly',
                    'execution_time': execution_time,
                    'execution_day': day_mapping.get(dayofweek, f'Day {dayofweek}')
                }

            if any_weekday:
                try:
                    return {
                        'schedule_type': 'monthly',
                        'execution_time': execution_time,
                        'execution_day': int(day)
                    }
                except ValueError:
                    pass  # Not a plain day of month: treated as a custom schedule

            # Complex/custom schedule
            return {
                'schedule_type': 'custom',
                'execution_time': execution_time,
                'cron_expression': cron_expression
            }

        except Exception as e:
            logger.error(f"Error parsing cron expression '{cron_expression}': {str(e)}")
            return {
                'schedule_type': 'custom',
                'execution_time': None,
                'cron_expression': cron_expression
            }

    @staticmethod
    def _cron_execution_time(hour: str, minute: str) -> Optional[str]:
        """Format cron hour/minute fields as HH:MM, or None if they are not plain numbers."""
        try:
            hour_int = int(hour) if hour != '*' else 0
            minute_int = int(minute) if minute != '*' else 0
            return f"{hour_int:02d}:{minute_int:02d}"
        except ValueError:
            return None

    def _build_cron_expression(self, schedule_config: Dict[str, Any]) -> str:
        """
        Build Quartz cron expression from schedule configuration
        
        Quartz Cron Format: second minute hour day month dayofweek year
        - Unix cron uses 5 fields: minute hour day month dayofweek
        - Quartz uses 7 fields: second minute hour day month dayofweek year
        - Use ? for day-of-month or day-of-week when the other is specified
        
        Args:
            schedule_config: Schedule configuration
            
        Returns:
            Quartz cron expression string (7 fields)
        """
        schedule_type = schedule_config.get('schedule_type', 'custom')
        
        if schedule_type == 'custom':
            # User provided custom cron expression
            custom_cron = schedule_config.get('cron_expression', '0 0 0 * * ?')
            # If user provided Unix cron (5 fields), convert to Quartz (7 fields)
            parts = custom_cron.split()
            if len(parts) == 5:
                # Unix: minute hour day month dayofweek
                # Quartz: second minute hour day month dayofweek year
                return f"0 {custom_cron} *"  # Add second=0 at start, year=* at end
            return custom_cron
        
        # Build Quartz cron from schedule type
        execution_time = schedule_config.get('execution_time', '00:00')
        hour, minute = execution_time.split(':') if ':' in execution_time else ('0', '0')
        
        if schedule_type == 'daily':
            # Every day at specified time: 0 minute hour * * ? *
            return f"0 {minute} {hour} * * ? *"
        
        elif schedule_type == 'weekly':
            # Quartz day-of-week: 1=Sunday, 2=Monday, ..., 7=Saturday
            day_mapping = {
                'Sunday': '1', 'Monday': '2', 'Tuesday': '3', 
                'Wednesday': '4', 'Thursday': '5', 'Friday': '6', 'Saturday': '7'
            }
            execution_day = schedule_config.get('execution_day', 'Monday')
            day_number = day_mapping.get(execution_day, '2')  # Default to Monday
            # Specific day of week: 0 minute hour ? * dayofweek *
            return f"0 {minute} {hour} ? * {day_number} *"
        
        elif schedule_type == 'monthly':
            execution_day = schedule_config.get('execution_day', 1)
            # Specific day of month: 0 minute hour day * ? *
            return f"0 {minute} {hour} {execution_day} * ? *"
        
        # Default: daily at midnight
        return "0 0 0 * * ? *"
    
    def update_job(self, job_id: int, job_update_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update job configuration (for 3-layer architecture auto-save)
        
        Args:
            job_id: Job ID
            job_update_data: Dictionary with fields to update
            
        Returns:
            Result dictionary with status
        """
        try:
            logger.info(f"Updating job {job_id} with data: {job_update_data}")
            
            # Call repository to update
            success = self.repository.update_job(job_id, job_update_data)
            
            if success:
                logger.info(f"Job {job_id} updated successfully")
                return {
                    "status": "success",
                    "message": "Job updated successfully",
                    "job_id": job_id
                }
            else:
                logger.error(f"Failed to update job {job_id}")
                return {
                    "status": "error",
                    "message": "Failed to update job in database"
                }
        except Exception as e:
            logger.error(f"Error updating job {job_id}: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Error updating job: {str(e)}"
            }
    
    def get_jobs_by_project(self, project_id: int) -> Dict[str, Any]:
        """
        Get all jobs for a project (3-layer architecture)
        
        Args:
            project_id: Project ID
            
        Returns:
            Result dictionary with jobs list
        """
        try:
            logger.info(f"Fetching jobs for project {project_id}")
            jobs = self.repository.get_jobs_by_project(project_id)
            logger.info(f"Found {len(jobs)} jobs for project {project_id}")

            # For each job, fetch last execution status
            for job in jobs:
                executions = self.repository.get_job_executions(job.get('id'), limit=1)
                if executions:
                    job['last_run_status'] = executions[0].get('status')
                    job['last_run_at'] = executions[0].get('start_time')
                else:
                    job['last_run_status'] = None
                    job['last_run_at'] = None

            return {
                "status": "success",
                "jobs": jobs,
                "count": len(jobs)
            }
        except Exception as e:
            logger.error(f"Error fetching jobs for project {project_id}: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Error fetching jobs: {str(e)}",
                "jobs": []
            }
    
    def create_new_job(self, project_id: int, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new job for a project (3-layer architecture)
        
        Args:
            project_id: Project ID
            job_data: Job configuration data
            
        Returns:
            Result dictionary with job_id
        """
        try:
            logger.info("Creating new job for project %s: %s",
                        str(project_id).replace('\n', '_').replace('\r', '_'),
                        str(job_data.get('job_name', '')).replace('\n', '_').replace('\r', '_'))
            
            # Create job configuration
            job_config = {
                "job_name": job_data.get("job_name", "Untitled Job"),
                "description": job_data.get("job_description", ""),
                "step": job_data.get("step", 1),
                "source_type": job_data.get("source_type"),
                "source_config": job_data.get("source_config"),
                "quality_config": job_data.get("quality_config"),
                "schedule_cron": job_data.get("schedule_cron"),
                "schedule_timezone": job_data.get("schedule_timezone", "UTC"),
                "deployed_by": job_data.get("deployed_by"),
                "is_primary": job_data.get("is_primary", False),
                "status": job_data.get("status", "pending")  # Support draft status
            }
            
            job_id = self.repository.create_job(project_id, job_config)
            
            if job_id:
                logger.info(f"Job created successfully with ID: {job_id}")
                return {
                    "status": "success",
                    "message": "Job created successfully",
                    "job_id": job_id
                }
            else:
                logger.error(f"Failed to create job for project {project_id}")
                return {
                    "status": "error",
                    "message": "Failed to create job in database"
                }
        except Exception as e:
            logger.error(f"Error creating job for project {project_id}: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Error creating job: {str(e)}"
            }
    
    def get_job_by_id(self, job_id: int) -> Dict[str, Any]:
        """
        Get job details by ID (3-layer architecture)
        
        Args:
            job_id: Job ID
            
        Returns:
            Result dictionary with job data
        """
        try:
            logger.info(f"Fetching job {job_id}")
            
            job = self.repository.get_job_by_id(job_id)
            
            if not job:
                logger.warning(f"Job {job_id} not found")
                return {
                    "status": "error",
                    "message": JOB_NOT_FOUND
                }

            logger.info(f"Found job {job_id}: {job.get('job_name')}")

            # Parse JSON fields if they're strings
            if job.get('source_config') and isinstance(job['source_config'], str):
                job['source_config'] = self._parse_source_config(job_id, job['source_config'])
            if job.get('quality_config') and isinstance(job['quality_config'], str):
                job['quality_config'] = self._parse_quality_config(job['quality_config'])
            self._apply_schedule_details(job_id, job)

            return {
                "status": "success",
                "job": job  # Changed from "data" to "job" to match frontend expectation
            }
        except Exception as e:
            logger.error(f"Error fetching job {job_id}: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Error fetching job: {str(e)}"
            }

    @staticmethod
    def _parse_source_config(job_id: int, raw: str) -> Dict[str, Any]:
        """Parse the stored source_config JSON, repairing legacy escaping when needed."""
        import json
        try:
            logger.info(f"[JSON PARSE] Parsing source_config for job {job_id}")
            logger.info(f"[JSON PARSE] Raw source_config string: {raw[:200]}...")
            return json.loads(raw)
        except Exception as e:
            logger.error(f"[JSON PARSE] Failed to parse source_config: {str(e)}")
            logger.error(f"[JSON PARSE] Raw string was: {raw}")

        try:
            # Fix double-escaped backslashes from legacy storage
            # e.g. "quote_char": "\\"" -> "quote_char": "\""
            sanitized = raw.replace('\\\\"', '\\"')
            # Fix unescaped quote in quote_char field
            # Pattern: "quote_char": """ -> "quote_char": "\""
            sanitized = re.sub(r'"quote_char":\s*"""', r'"quote_char": "\\""', sanitized)
            parsed = json.loads(sanitized)
            logger.info("[JSON PARSE] Successfully parsed after sanitization")
            return parsed
        except Exception as e2:
            logger.error(f"[JSON PARSE] Sanitization also failed: {str(e2)}")
            return {}

    @staticmethod
    def _parse_quality_config(raw: str) -> Dict[str, Any]:
        import json
        try:
            return json.loads(raw)
        except Exception as e:
            logger.error(f"[JSON PARSE] Failed to parse quality_config: {str(e)}")
            return {}

    def _apply_schedule_details(self, job_id: int, job: Dict[str, Any]) -> None:
        """Add the parsed schedule fields (type, time, day) to the job dict."""
        if not job.get('schedule_cron'):
            job['schedule_type_parsed'] = 'manual'
            job['execution_time_parsed'] = None
            job['execution_day_parsed'] = None
            return

        parsed_schedule = self._parse_cron_expression(job['schedule_cron'])
        job['schedule_type_parsed'] = parsed_schedule.get('schedule_type')
        job['execution_time_parsed'] = parsed_schedule.get('execution_time')
        job['execution_day_parsed'] = parsed_schedule.get('execution_day')
        logger.info(f"[SCHEDULE PARSE] Job {job_id}: {parsed_schedule}")
    
    def delete_job(self, job_id: int) -> Dict[str, Any]:
        """
        Delete a job by ID
        
        Args:
            job_id: Job ID to delete
            
        Returns:
            Result dictionary with status
        """
        try:
            logger.info(f"Deleting job {job_id}")
            
            success = self.repository.delete_job(job_id)
            
            if success:
                logger.info(f"Job {job_id} deleted successfully")
                return {
                    "status": "success",
                    "message": "Job deleted successfully"
                }
            else:
                logger.error(f"Failed to delete job {job_id}")
                return {
                    "status": "error",
                    "message": "Failed to delete job"
                }
        except Exception as e:
            logger.error(f"Error deleting job {job_id}: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Error deleting job: {str(e)}"
            }
    
    def get_job_report(self, job_id: int) -> Dict[str, Any]:
        """
        Get job execution report from summary table
        
        Args:
            job_id: Job ID
            
        Returns:
            Result dictionary with report data
        """
        try:
            logger.info(f"Fetching report for job {job_id}")
            settings = Settings()
            catalog_name = settings.uc_catalog
            results_schema = settings.uc_results_schema
            
            # Get job details to extract project and job names
            job = self.repository.get_job_by_id(job_id)
            
            if not job:
                logger.warning(f"Job {job_id} not found")
                return {
                    "status": "not_found",
                    "message": JOB_NOT_FOUND
                }
            
            job_name = job.get('job_name', '')
            project_id = job.get('project_id')
            
            # Get project name
            from database.repositories import ProjectRepository
            project = ProjectRepository.get_project_by_id(project_id)
            
            if not project:
                logger.warning(f"Project {project_id} not found")
                return {
                    "status": "not_found",
                    "message": PROJECT_NOT_FOUND
                }
            
            project_name = project.get('project_name', '')
            
            # Build table names from project + job (raw names from DB)
            norm_project = self._normalize_name(project_name)
            norm_job = self._normalize_name(job_name)
            table_name = f"{catalog_name}.{results_schema}.dq_{norm_project}_{norm_job}_summary_dataset"
            
            logger.info(f"[REPORT] 📊 Fetching data from table: {table_name}")
            
            # Use existing db_utils connection (handles OAuth automatically)
            from db_utils import get_db_connection
            
            columns_table_name = f"{catalog_name}.{results_schema}.dq_{norm_project}_{norm_job}_summary_columns"

            # Connect and query using db_utils
            try:
                with get_db_connection() as conn:
                    with conn.cursor() as cursor:
                        query = f"""
                        SELECT 
                            check_type,
                            dataset_score,
                            dataset_status,
                            total_columns,
                            columns_ok,
                            columns_warning,
                            columns_ko,
                            execution_timestamp
                        FROM {table_name}
                        WHERE CAST(execution_timestamp AS TIMESTAMP) = (
                            SELECT MAX(CAST(execution_timestamp AS TIMESTAMP)) FROM {table_name}
                        )
                        """
                        cursor.execute(query)
                        
                        # Fetch results
                        cols = [desc[0] for desc in cursor.description]
                        rows = cursor.fetchall()
                        
                        # Convert to list of dicts
                        data = []
                        for row in rows:
                            data.append(dict(zip(cols, row)))
                        
                        logger.info(f"[REPORT] ✅ Fetched {len(data)} rows from summary table")

                        # Fetch faulty_count + total_rows from _summary_columns (latest run)
                        faulty_by_check, total_rows_analysed = self._fetch_faulty_counts(cursor, columns_table_name)

                        return {
                            "status": "success",
                            "data": data,
                            "faulty_by_check": faulty_by_check,
                            "total_rows_analysed": total_rows_analysed,
                            "table_name": table_name
                        }
            except Exception as db_error:
                # Check if table doesn't exist
                error_msg = str(db_error).lower()
                if 'table_or_view_not_found' in error_msg or 'table or view not found' in error_msg:
                    logger.warning(f"[REPORT] ⚠️ Summary table not found: {table_name}")
                    return {
                        "status": "not_found",
                        "message": f"Report table not found. Please run the job first.",
                        "table_name": table_name
                    }
                else:
                    # Re-raise other database errors
                    raise
                    
        except Exception as e:
            logger.error(f"[REPORT] ❌ Error fetching report for job {job_id}: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Error fetching report: {str(e)}"
            }
    
    @staticmethod
    def _fetch_faulty_counts(cursor, columns_table_name: str) -> Tuple[Dict[str, int], Optional[int]]:
        """Faulty row counts per check type and rows analysed, from the latest run of _summary_columns."""
        faulty_by_check: Dict[str, int] = {}
        total_rows_analysed = None
        try:
            cursor.execute(f"""
                SELECT check_type, SUM(faulty_count) AS total_faulty, MAX(total_rows) AS total_rows
                FROM {columns_table_name}
                WHERE CAST(execution_timestamp AS TIMESTAMP) = (
                    SELECT MAX(CAST(execution_timestamp AS TIMESTAMP)) FROM {columns_table_name}
                )
                GROUP BY check_type
                """)
            for check_type, total_faulty, total_rows in cursor.fetchall():
                faulty_by_check[check_type] = int(total_faulty) if total_faulty is not None else 0
                # total_rows is the same across all rows — take first non-null
                if total_rows_analysed is None and total_rows is not None:
                    total_rows_analysed = int(total_rows)
            logger.info(f"[REPORT] ✅ Fetched faulty counts: {faulty_by_check}, total_rows={total_rows_analysed}")
        except Exception as col_err:
            logger.warning(f"[REPORT] ⚠️ Could not fetch faulty counts: {col_err}")
        return faulty_by_check, total_rows_analysed

    def download_faulty_records(self, job_id: int) -> Dict[str, Any]:
        """
        Download faulty records as CSV for a given job.
        Derives the table name from job/project names — no need to pass it explicitly.
        """
        try:
            job = self.repository.get_job_by_id(job_id)
            if not job:
                return {"status": "error", "message": JOB_NOT_FOUND}

            job_name   = job.get('job_name', '')
            project_id = job.get('project_id')

            from database.repositories import ProjectRepository
            project = ProjectRepository.get_project_by_id(project_id)
            if not project:
                return {"status": "error", "message": PROJECT_NOT_FOUND}

            project_name = project.get('project_name', '')
            # Build table name from project + job (raw names from DB)
            norm_project = self._normalize_name(project_name)
            norm_job = self._normalize_name(job_name)
            settings = Settings()
            table_name = f"{settings.uc_catalog}.{settings.uc_results_schema}.dq_{norm_project}_{norm_job}_dq_faulty_records"
            logger.info(f"[DOWNLOAD] 📥 Fetching faulty records from: {table_name}")

            from db_utils import get_db_connection
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    query = f"""
                    SELECT *
                    FROM {table_name}
                    ORDER BY failure_count DESC, row_id
                    """
                    cursor.execute(query)
                    cols = [desc[0] for desc in cursor.description]
                    rows = cursor.fetchall()

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(cols)
            for row in rows:
                writer.writerow(row)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Filename uses job_name which already includes project prefix
            filename  = f"faulty_records_{norm_project}_{norm_job}_{timestamp}.csv"

            return {
                "status":      "success",
                "csv_content": output.getvalue(),
                "filename":    filename,
                "row_count":   len(rows)
            }

        except Exception as e:
            error_msg = str(e).lower()
            if 'table_or_view_not_found' in error_msg or 'table or view not found' in error_msg:
                return {"status": "not_found", "message": "Faulty records table not found. Please run the job first."}
            logger.error(f"[DOWNLOAD] ❌ Error: {str(e)}", exc_info=True)
            return {"status": "error", "message": f"Failed to download faulty records: {str(e)}"}

    def publish_to_openmetadata(self, job_id: int, omd_fqn: str) -> Dict[str, Any]:
        """
        Publish DQ results for the latest run of a job to OpenMetadata.
        Triggers a Databricks notebook run on a job cluster (internal network)
        so the cluster can reach the OMD intranet API — serverless cannot.
        Also persists the FQN in dq_jobs.omd_fqn for future pre-fill.
        """
        try:
            # Resolve job + project names
            job = self.repository.get_job_by_id(job_id)
            if not job:
                return {"status": "error", "message": JOB_NOT_FOUND}

            job_name   = job.get('job_name', '')
            project_id = job.get('project_id')

            from database.repositories import ProjectRepository
            project = ProjectRepository.get_project_by_id(project_id)
            if not project:
                return {"status": "error", "message": PROJECT_NOT_FOUND}

            project_name = project.get('project_name', '')
            norm_project = self._normalize_name(project_name)
            norm_job     = self._normalize_name(job_name)

            # Persist the FQN for future pre-fill
            from database.repositories.job_repository import JobRepository
            JobRepository.update_omd_fqn(job_id, omd_fqn)

            # Submit notebook run on a job cluster (NOT serverless)
            return self._submit_omd_notebook(norm_project, norm_job, omd_fqn, dq_job_id=job_id)

        except Exception as e:
            logger.error(f"[OMD] publish_to_openmetadata error: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def _get_omd_notebook_paths(self) -> Tuple[str, str]:
        """Return the payload-preparation notebook and the OpenMetadata push notebook paths."""
        payload_notebook = os.getenv("OMD_PAYLOAD_NOTEBOOK_PATH", "/Workspace/Shared/notebooks/prepare_dq_payload").strip()
        push_notebook = os.getenv("OMD_PUSH_NOTEBOOK_PATH", os.getenv("OMD_NOTEBOOK_PATH", DEFAULT_OMD_PUSH_NOTEBOOK_PATH)).strip()
        return (
            payload_notebook or "/Workspace/Shared/notebooks/prepare_dq_payload",
            push_notebook or DEFAULT_OMD_PUSH_NOTEBOOK_PATH,
        )

    def _build_omd_notebook_params(self, norm_project: str, norm_job: str, omd_fqn: str, omd_base_url: str, push_notebook_path: str = "") -> Dict[str, str]:
        """Build notebook parameters for the OMD publishing notebook chain."""
        return {
            "norm_project": norm_project,
            "norm_job": norm_job,
            "omd_fqn": omd_fqn,
            "omd_base_url": omd_base_url,
            "databricks_host": os.getenv("DATABRICKS_SERVER_HOSTNAME", ""),
            "databricks_http_path": os.getenv("DATABRICKS_HTTP_PATH", ""),
            "omd_push_notebook_path": push_notebook_path or os.getenv("OMD_PUSH_NOTEBOOK_PATH", os.getenv("OMD_NOTEBOOK_PATH", DEFAULT_OMD_PUSH_NOTEBOOK_PATH)),
        }

    def _submit_omd_notebook(self, norm_project: str, norm_job: str, omd_fqn: str, dq_job_id: int = 0) -> Dict[str, Any]:
        """
        Submit the push_dq_to_omd notebook on a job cluster and poll until done.
        Polling: every 10 s, up to 10 min max.
        """
        import time as _time

        payload_notebook_path, push_notebook_path = self._get_omd_notebook_paths()
        notebook_path = payload_notebook_path
        omd_base_url  = os.getenv("OMD_BASE_URL", "https://openmetadata.intranet.geodis.org/api")

        if not os.getenv("OMD_TOKEN", ""):
            return {"status": "error", "message": "OMD_TOKEN environment variable not set"}

        params = self._build_omd_notebook_params(norm_project, norm_job, omd_fqn, omd_base_url, push_notebook_path)

        # Create a two-task Databricks job where task 1 runs on serverless and
        # task 2 runs on the configured job cluster and receives the payload as task parameters.
        payload = {
            "job_name": f"omd_publish_{norm_project}_{norm_job}",
            "norm_project": norm_project,
            "norm_job": norm_job,
            "omd_fqn": omd_fqn,
            "omd_base_url": omd_base_url,
            "prepare_notebook_path": payload_notebook_path,
            "push_notebook_path": push_notebook_path,
            "payload_json": "",
        }

        submit_result = self.databricks_service.create_omd_two_task_job(payload)
        if submit_result.get("status") != "success":
            return {"status": "error", "message": f"Failed to create OMD job: {submit_result.get('message')}"}

        job_id  = submit_result.get("job_id", "")
        run_id  = submit_result.get("run_id", "")
        run_url = submit_result.get("run_url", submit_result.get("job_url", ""))
        logger.info(f"[OMD] Two-task job submitted — job_id={job_id}, run_id={run_id}, url={run_url}")

        # Persist the OMD execution in DB for tracking
        from database.repositories.job_repository import JobRepository
        omd_exec_id = JobRepository.create_omd_execution(
            job_id=dq_job_id,
            omd_fqn=omd_fqn,
            databricks_job_id=job_id,
            databricks_run_id=run_id,
            run_url=run_url,
        )
        logger.info(f"[OMD] Execution record created — omd_exec_id={omd_exec_id}")

        # Return immediately — do not poll. The caller can track the run via run_url.
        return {
            "status":      "submitted",
            "message":     "OMD publish job submitted. Check the Databricks run for progress.",
            "job_id":      job_id,
            "run_id":      run_id,
            "run_url":     run_url,
            "fqn":         omd_fqn,
            "omd_exec_id": omd_exec_id,
        }

    def _normalize_name(self, name: str) -> str:
        """Normalize a project/job name for table naming.

        Must produce the same result as sanitize_name() in every Databricks notebook
        so that the backend looks up the exact table the notebook wrote:
            re.sub(r'[^a-zA-Z0-9_]', '_', name).lower()
        """
        normalized = re.sub(r'[^a-zA-Z0-9_]', '_', name).lower()
        return normalized
