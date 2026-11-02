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
Databricks Service - Wrapper around databricks_jobs.py
Provides a clean interface to Databricks job management
"""
from typing import Dict, Any, Optional
from databricks_jobs import DatabricksJobManager


class DatabricksService:
    """Service for Databricks job operations"""
    
    def __init__(self):
        self.job_manager = DatabricksJobManager()
    
    def create_job(self, job_config: Dict[str, Any], tasks_config: list) -> Dict[str, Any]:
        """
        Create a Databricks job with tasks
        
        Args:
            job_config: Job configuration dictionary
            tasks_config: List of task configurations
            
        Returns:
            Dictionary with status and job information
        """
        try:
            # Build project config for DatabricksJobManager
            # This adapts our service layer format to what DatabricksJobManager expects
            project_config = {
                'dataset_name': job_config.get('job_name', 'DQ_Job'),
                'source_type': 'unity_catalog',  # Default
            }
            
            # Build payload in the format expected by DatabricksJobManager
            component_configs = {}
            for control in tasks_config:
                component_id = control.get('component_id')
                if component_id:
                    component_configs[component_id] = control.get('config', {})

            payload = {
                'deployment': job_config,
                'quality_controls': {
                    'enabled_components': tasks_config,
                    'component_configs': component_configs
                }
            }
            
            result = self.job_manager.create_dq_job(project_config, payload)
            
            return result
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Failed to create Databricks job: {str(e)}'
            }
    
    def run_job(self, databricks_job_id: str, parameters: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Run a Databricks job
        
        Args:
            databricks_job_id: Databricks job ID
            parameters: Optional parameters for the job
            
        Returns:
            Dictionary with status and run information
        """
        try:
            result = self.job_manager.run_job(databricks_job_id, parameters)
            
            # Add run URL if not present
            if result.get('status') == 'success' and 'run_url' not in result:
                run_id = result.get('run_id')
                if run_id and self.job_manager.host:
                    result['run_url'] = f"https://{self.job_manager.host}/jobs/{databricks_job_id}/runs/{run_id}"
            
            return result
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Failed to run job: {str(e)}'
            }
    
    def get_run_status(self, run_id: str) -> Dict[str, Any]:
        """
        Get status of a job run
        
        Args:
            run_id: Databricks run ID
            
        Returns:
            Dictionary with status and run information
        """
        try:
            return self.job_manager.get_run_status(run_id)
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Failed to get run status: {str(e)}'
            }
    
    def get_run_output(self, run_id: str) -> Dict[str, Any]:
        """
        Get output/results from a completed job run
        
        Args:
            run_id: Databricks run ID
            
        Returns:
            Dictionary with run results
        """
        try:
            return self.job_manager.get_run_output(run_id)
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Failed to get run output: {str(e)}'
            }

    def create_omd_two_task_job(self, payload: Dict[str, str]) -> Dict[str, Any]:
        """Create a two-task Databricks job for the OMD DQ publish flow."""
        try:
            return self.job_manager.create_omd_two_task_job(payload)
        except Exception as e:
            return {'status': 'error', 'message': f'Failed to create OMD two-task job: {str(e)}'}

    def submit_omd_notebook_run(self, notebook_path: str, params: Dict[str, str]) -> Dict[str, Any]:
        """
        Submit a one-time notebook run on a job cluster for the OMD DQ push.
        Delegates to DatabricksJobManager.submit_omd_notebook_run().
        """
        try:
            return self.job_manager.submit_omd_notebook_run(notebook_path, params)
        except Exception as e:
            return {'status': 'error', 'message': f'Failed to submit OMD notebook run: {str(e)}'}

    def delete_job(self, databricks_job_id: str) -> Dict[str, Any]:
        """
        Delete a Databricks job
        
        Args:
            databricks_job_id: Databricks job ID
            
        Returns:
            Dictionary with status
        """
        try:
            return self.job_manager.delete_job(databricks_job_id)
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Failed to delete job: {str(e)}'
            }    
    def update_job_schedule(self, databricks_job_id: str, cron_expression: str, 
                           timezone: str = 'UTC', pause_status: str = 'UNPAUSED') -> Dict[str, Any]:
        """
        Update Databricks job schedule
        
        Args:
            databricks_job_id: Databricks job ID
            cron_expression: Quartz cron expression
            timezone: Timezone for schedule
            pause_status: PAUSED or UNPAUSED
            
        Returns:
            Dictionary with status
        """
        try:
            return self.job_manager.update_job_schedule(
                databricks_job_id, cron_expression, timezone, pause_status
            )
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Failed to update job schedule: {str(e)}'
            }
