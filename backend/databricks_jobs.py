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
Databricks Job Creation and Management
Handles creation of Databricks jobs with tasks for each DQ check
"""
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs
from typing import Dict, List, Any, Optional
import os
import json
import requests as _requests

OMD_BASE_URL = os.getenv("OMD_BASE_URL", "")
CONTENT_TYPE_JSON = "application/json"


class DatabricksJobManager:
    """Manages Databricks job creation and execution for Data Quality checks"""
    
    def __init__(self):
        """Initialize Databricks workspace client"""
        self._client = None
        self.host = ''
    
    @property
    def client(self):
        """Lazy initialization of Databricks client"""
        if self._client is None:
            try:
                from config.databricks_auth import get_workspace_client, get_host
                
                print(f"[DATABRICKS] Initializing client via Service Principal...")
                self._client = get_workspace_client()
                self.host = get_host()
                
                current_user = self._client.current_user.me()
                print(f"[DATABRICKS] ✅ Connected as: {current_user.user_name}")
                print(f"[DATABRICKS] ✅ Host: {self.host}")
                
            except Exception as e:
                print(f"[DATABRICKS] ❌ Initialization failed: {e}")
                import traceback
                traceback.print_exc()
                raise RuntimeError(f"Failed to initialize Databricks client: {e}") from e
        
        return self._client
    
    def create_dq_job(self, project_config: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a Databricks job with tasks for each enabled DQ check
        
        Args:
            project_config: Project configuration from database
            payload: DQ payload with quality controls
            
        Returns:
            Dict with job_id and creation details
        """
        print("[CREATE_DQ_JOB] Attempting to create Databricks job...")
        
        try:
            # Extract configuration
            job_name = payload['deployment'].get('job_name', f"DQ_{project_config['dataset_name']}")
            dataset_name = project_config['dataset_name']
            source_type = project_config['source_type']
            
            # Build tasks from enabled quality controls
            tasks = self._build_tasks_from_controls(payload['quality_controls'], project_config)
            
            if not tasks:
                return {
                    'status': 'error',
                    'message': 'No enabled quality controls to create tasks'
                }
            
            # Create job configuration
            job_config = self._build_job_config(
                job_name=job_name,
                tasks=tasks,
                project_config=project_config,
                payload=payload
            )
            
            # Create job in Databricks
            created_job = self.client.jobs.create(**job_config)
            
            return {
                'status': 'success',
                'job_id': str(created_job.job_id),
                'job_name': job_name,
                'tasks_count': len(tasks),
                'message': f'Databricks job created with {len(tasks)} tasks'
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Failed to create Databricks job: {str(e)}'
            }
    
    def _build_tasks_from_controls(self, quality_controls: Dict[str, Any], project_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Build Databricks task definitions from quality controls
        
        Each enabled check becomes a task in the Databricks job
        """
        tasks = []
        task_dependencies = []  # Track dependencies between tasks
        
        # Get enabled components
        enabled_components = quality_controls.get('enabled_components', [])
        component_configs = quality_controls.get('component_configs', {})
        
        for component in enabled_components:
            component_id = component['id']
            component_name = component['name']
            
            # Get component-specific configuration
            comp_config = component_configs.get(component_id, {})
            
            # Build tasks based on component type
            if component_id == 'completeness_check':
                tasks.extend(self._build_completeness_tasks(
                    component, comp_config, project_config
                ))
            elif component_id == 'uniqueness_check':
                tasks.extend(self._build_uniqueness_tasks(
                    component, comp_config, project_config
                ))
            elif component_id == 'consistency_check':
                tasks.extend(self._build_consistency_tasks(
                    component, comp_config, project_config
                ))
            elif component_id == 'validity_check':
                tasks.extend(self._build_validity_tasks(
                    component, comp_config, project_config
                ))
            elif component_id == 'custom_sql_check':
                tasks.extend(self._build_custom_sql_tasks(
                    component, comp_config, project_config
                ))
            elif 'accuracy' in component_id.lower():
                tasks.extend(self._build_accuracy_tasks(
                    component, comp_config, project_config
                ))
        
        return tasks
    
    def _build_completeness_tasks(self, component: Dict, config: Dict, project_config: Dict) -> List[Dict[str, Any]]:
        """Build tasks for completeness checks (null checks per column)"""
        tasks = []
        
        null_checks = config.get('null_checks', [])
        for check in null_checks:
            column = check['column']
            threshold = check.get('threshold', 95.0)
            
            task = self._create_task_definition(
                task_key=f"completeness_{column}",
                task_name=f"Completeness Check - {column}",
                notebook_path="/Workspace/dq_notebooks/completeness_check",
                parameters={
                    'source_type': project_config['source_type'],
                    'catalog': project_config.get('catalog', ''),
                    'schema': project_config.get('schema', ''),
                    'table': project_config.get('table', ''),
                    'file_path': project_config.get('file_path', ''),
                    'column': column,
                    'threshold': threshold,
                    'check_type': 'null_check'
                }
            )
            tasks.append(task)
        
        return tasks
    
    def _build_uniqueness_tasks(self, component: Dict, config: Dict, project_config: Dict) -> List[Dict[str, Any]]:
        """Build tasks for uniqueness checks"""
        tasks = []
        
        uniqueness_checks = config.get('uniqueness_checks', [])
        for check in uniqueness_checks:
            columns = check['columns']
            threshold = check.get('threshold', 100.0)
            
            column_list = ','.join(columns)
            task = self._create_task_definition(
                task_key=f"uniqueness_{column_list.replace(',', '_')}",
                task_name=f"Uniqueness Check - {column_list}",
                notebook_path="/Workspace/dq_notebooks/uniqueness_check",
                parameters={
                    'source_type': project_config['source_type'],
                    'catalog': project_config.get('catalog', ''),
                    'schema': project_config.get('schema', ''),
                    'table': project_config.get('table', ''),
                    'file_path': project_config.get('file_path', ''),
                    'columns': column_list,
                    'threshold': threshold,
                    'check_type': 'uniqueness_check'
                }
            )
            tasks.append(task)
        
        return tasks
    
    def _build_consistency_tasks(self, component: Dict, config: Dict, project_config: Dict) -> List[Dict[str, Any]]:
        """Build tasks for consistency checks"""
        tasks = []
        
        consistency_checks = config.get('consistency_checks', [])
        for check in consistency_checks:
            check_type = check['type']
            columns = check.get('columns', [])
            threshold = check.get('threshold', 95.0)
            
            task = self._create_task_definition(
                task_key=f"consistency_{check_type}_{len(tasks)}",
                task_name=f"Consistency Check - {check_type}",
                notebook_path="/Workspace/dq_notebooks/consistency_check",
                parameters={
                    'source_type': project_config['source_type'],
                    'catalog': project_config.get('catalog', ''),
                    'schema': project_config.get('schema', ''),
                    'table': project_config.get('table', ''),
                    'file_path': project_config.get('file_path', ''),
                    'check_type': check_type,
                    'columns': ','.join(columns) if columns else '',
                    'threshold': threshold
                }
            )
            tasks.append(task)
        
        return tasks
    
    def _build_validity_tasks(self, component: Dict, config: Dict, project_config: Dict) -> List[Dict[str, Any]]:
        """Build tasks for validity/format checks"""
        tasks = []
        
        validity_checks = config.get('validity_checks', [])
        for check in validity_checks:
            column = check['column']
            rule_type = check['type']
            threshold = check.get('threshold', 95.0)
            pattern = check.get('pattern', '')
            
            task = self._create_task_definition(
                task_key=f"validity_{column}_{rule_type}",
                task_name=f"Validity Check - {column} ({rule_type})",
                notebook_path="/Workspace/dq_notebooks/validity_check",
                parameters={
                    'source_type': project_config['source_type'],
                    'catalog': project_config.get('catalog', ''),
                    'schema': project_config.get('schema', ''),
                    'table': project_config.get('table', ''),
                    'file_path': project_config.get('file_path', ''),
                    'column': column,
                    'rule_type': rule_type,
                    'pattern': pattern,
                    'threshold': threshold,
                    'check_type': 'validity_check'
                }
            )
            tasks.append(task)
        
        return tasks
    
    def _build_custom_sql_tasks(self, component: Dict, config: Dict, project_config: Dict) -> List[Dict[str, Any]]:
        """Build tasks for custom SQL checks"""
        tasks = []
        
        custom_checks = config.get('custom_checks', [])
        for idx, check in enumerate(custom_checks):
            sql_query = check['query']
            threshold = check.get('threshold', 95.0)
            
            task = self._create_task_definition(
                task_key=f"custom_sql_{idx}",
                task_name=f"Custom SQL Check {idx + 1}",
                notebook_path="/Workspace/dq_notebooks/custom_sql_check",
                parameters={
                    'source_type': project_config['source_type'],
                    'catalog': project_config.get('catalog', ''),
                    'schema': project_config.get('schema', ''),
                    'table': project_config.get('table', ''),
                    'file_path': project_config.get('file_path', ''),
                    'sql_query': sql_query,
                    'threshold': threshold,
                    'check_type': 'custom_sql'
                }
            )
            tasks.append(task)
        
        return tasks

    def _build_accuracy_tasks(self, component: Dict, config: Dict, project_config: Dict) -> List[Dict[str, Any]]:
        """Build tasks for structured accuracy checks"""
        tasks = []

        custom_rules = config.get('custom_rules', [])
        if not custom_rules:
            return tasks

        task = self._create_task_definition(
            task_key="accuracy_custom_rules",
            task_name="Accuracy Check",
            notebook_path="/Workspace/dq_notebooks/accuracy_check",
            parameters={
                'source_type': project_config['source_type'],
                'catalog': project_config.get('catalog', ''),
                'schema': project_config.get('schema', ''),
                'table': project_config.get('table', ''),
                'file_path': project_config.get('file_path', ''),
                'custom_rules_json': json.dumps(custom_rules),
                'check_type': 'accuracy_check'
            }
        )
        tasks.append(task)

        return tasks
    
    def _create_task_definition(self, task_key: str, task_name: str, notebook_path: str, parameters: Dict) -> Dict[str, Any]:
        """Create a single task definition for Databricks job"""
        return {
            'task_key': task_key,
            'description': task_name,
            'notebook_task': {
                'notebook_path': notebook_path,
                'base_parameters': parameters
            },
            'new_cluster': self._get_cluster_config(),
            'timeout_seconds': 3600,
            'max_retries': 2,
            'min_retry_interval_millis': 60000
        }
    
    def _get_cluster_config(self, env_vars: dict = None) -> Dict[str, Any]:
        """Get cluster configuration for tasks"""
        config = {
            'spark_version': '13.3.x-scala2.12',
            'node_type_id': 'Standard_D4s_v3',
            'num_workers': 2,
            'spark_conf': {
                'spark.databricks.delta.preview.enabled': 'true'
            },
        }
        if env_vars:
            config['spark_env_vars'] = env_vars
        return config
    
    def _build_job_config(self, job_name: str, tasks: List[Dict], project_config: Dict, payload: Dict) -> Dict[str, Any]:
        """Build complete job configuration"""
        return {
            'name': job_name,
            'tasks': [jobs.Task(**task) for task in tasks],
            'job_clusters': [],
            'email_notifications': {
                'on_failure': [],
                'on_success': []
            },
            'timeout_seconds': 0,
            'max_concurrent_runs': 1,
            'format': 'MULTI_TASK'
        }
    
    def run_job(self, job_id: str, notebook_params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Run a Databricks job
        
        Args:
            job_id: Databricks job ID
            notebook_params: Optional parameters to pass to notebooks
            
        Returns:
            Dict with run_id and status
        """
        try:
            print(f"[RUN_JOB] Attempting to run job {job_id}")
            run = self.client.jobs.run_now(job_id=int(job_id), notebook_params=notebook_params)
            print(f"[RUN_JOB] ✅ Job started, run_id={run.run_id}")
            
            return {
                'status': 'success',
                'run_id': str(run.run_id),
                'message': 'Job run submitted successfully'
            }
        except Exception as e:
            print(f"[RUN_JOB] ❌ Failed: {e}")
            return {
                'status': 'error',
                'message': f'Failed to run job: {str(e)}'
            }

    def create_omd_two_task_job(self, payload: Dict[str, str]) -> Dict[str, Any]:
        """Create a two-task Databricks job: task 1 serverless, task 2 job cluster."""
        try:
            from config.databricks_auth import get_access_token, get_host

            host = f"https://{get_host()}"
            token = get_access_token()
            print("[OMD_JOB] Creating two-task job for OMD publishing")

            task1_params = {
                "norm_project": payload.get("norm_project", ""),
                "norm_job": payload.get("norm_job", ""),
                "omd_fqn": payload.get("omd_fqn", ""),
                "omd_base_url": payload.get("omd_base_url", OMD_BASE_URL),
            }

            task2_params = {
                "norm_project": payload.get("norm_project", ""),
                "norm_job": payload.get("norm_job", ""),
                "omd_fqn": payload.get("omd_fqn", ""),
                "omd_base_url": payload.get("omd_base_url", OMD_BASE_URL),
                "payload_json": payload.get("payload_json", ""),
                "payload_path": payload.get("payload_path", ""),
            }

            serverless_task = {
                "task_key": "prepare_payload",
                "description": "Prepare DQ payload from Unity Catalog summary tables",
                "notebook_task": {
                    "notebook_path": payload.get("prepare_notebook_path", "/Workspace/Shared/notebooks/prepare_dq_payload"),
                    "base_parameters": task1_params,
                },
                "timeout_seconds": 1800,
                "max_retries": 0,
            }

            job_cluster_task = {
                "task_key": "push_to_omd",
                "description": "Push prepared payload to OpenMetadata",
                "depends_on": [{"task_key": "prepare_payload"}],
                "notebook_task": {
                    "notebook_path": payload.get("push_notebook_path", "/Workspace/Shared/notebooks/push_dq_to_omd"),
                    "base_parameters": task2_params,
                },
                "job_cluster_key": "omd_job_cluster",
                "timeout_seconds": 1800,
                "max_retries": 0,
            }

            # Inject secrets into the job cluster env so notebooks read them via os.getenv()
            # without exposing them as visible task parameters.
            cluster_env_vars = {
                "OMD_TOKEN": os.getenv("OMD_TOKEN", ""),
                "OMD_BASE_URL": os.getenv("OMD_BASE_URL", OMD_BASE_URL),
            }

            job_payload = {
                "name": payload.get("job_name", "omd_dq_publish"),
                "tasks": [serverless_task, job_cluster_task],
                "job_clusters": [{
                    "job_cluster_key": "omd_job_cluster",
                    "new_cluster": self._get_cluster_config(env_vars=cluster_env_vars),
                }],
                "format": "MULTI_TASK",
                "max_concurrent_runs": 1,
                "timeout_seconds": 0,
            }

            resp = _requests.post(
                f"{host}/api/2.1/jobs/create",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": CONTENT_TYPE_JSON
                },
                json=job_payload,
                timeout=30,
            )

            if resp.status_code in (200, 201):
                job_id = str(resp.json().get("job_id", ""))
                print(f"[OMD_JOB] ✅ Created job_id={job_id}")

                run_payload = {
                    "job_id": int(job_id),
                    "run_name": payload.get("job_name", "omd_dq_publish"),
                }

                run_resp = _requests.post(
                    f"{host}/api/2.1/jobs/run-now",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": CONTENT_TYPE_JSON
                    },
                    json=run_payload,
                    timeout=30,
                )

                if run_resp.status_code in (200, 201):
                    run_id = str(run_resp.json().get("run_id", ""))
                    run_url = f"{host}/#job/runs/{run_id}" if run_id else f"{host}/#job/{job_id}"
                    print(f"[OMD_JOB] ✅ Submitted run_id={run_id}")
                    return {
                        "status": "success",
                        "job_id": job_id,
                        "run_id": run_id,
                        "job_url": f"{host}/#job/{job_id}",
                        "run_url": run_url,
                    }

                print(f"[OMD_JOB] ❌ Failed to submit run ({run_resp.status_code}): {run_resp.text}")
                return {"status": "error", "message": f"jobs/run-now failed ({run_resp.status_code}): {run_resp.text}"}

            print(f"[OMD_JOB] ❌ Failed ({resp.status_code}): {resp.text}")
            return {"status": "error", "message": f"jobs/create failed ({resp.status_code}): {resp.text}"}

        except Exception as e:
            print(f"[OMD_JOB] ❌ Exception: {e}")
            return {"status": "error", "message": str(e)}

    def submit_omd_notebook_run(self, notebook_path: str, params: Dict[str, str]) -> Dict[str, Any]:
        """
        Submit a one-time notebook run on a job cluster (NOT serverless).
        Used for the OMD push so the cluster is on the internal network
        and can reach the OpenMetadata intranet API.

        Args:
            notebook_path: Workspace path to the notebook (e.g. /Workspace/Shared/...)
            params:        Notebook base_parameters dict
            user_token:   Optional user access token to run as the launching user

        Returns:
            Dict with run_id on success, or error message
        """
        try:
            from config.databricks_auth import get_access_token, get_host

            host  = f"https://{get_host()}"
            token = get_access_token()
            print("[OMD_SUBMIT] Submitting notebook run with service principal auth")

            spark_version = (os.getenv("OMD_CLUSTER_SPARK_VERSION") or "17.3.x-scala2.13").strip() or "17.3.x-scala2.13"
            instance_pool = os.getenv("OMD_CLUSTER_INSTANCE_POOL_ID", "0504-162430-guyed166-pool-xfba3u0i")
            driver_pool    = os.getenv("OMD_CLUSTER_DRIVER_INSTANCE_POOL_ID", "0504-162430-ameba152-pool-3ww7ikli")
            runtime_engine = os.getenv("OMD_CLUSTER_RUNTIME_ENGINE", "STANDARD")

            new_cluster = {
                "spark_version": spark_version,
                "num_workers": 1,
                "spark_conf": {
                    "spark.databricks.delta.preview.enabled": "true"
                },
                "runtime_engine": runtime_engine,
            }

            if instance_pool:
                new_cluster["instance_pool_id"] = instance_pool
            if driver_pool:
                new_cluster["driver_instance_pool_id"] = driver_pool

            payload = {
                "run_name": f"push_dq_to_omd",
                "tasks": [{
                    "task_key": "push_omd",
                    "notebook_task": {
                        "notebook_path": notebook_path,
                        "base_parameters": params
                    },
                    "new_cluster": new_cluster,
                    "timeout_seconds": 600
                }]
            }

            print(f"[OMD_SUBMIT] Submitting notebook run: {notebook_path}")
            resp = _requests.post(
                f"{host}/api/2.1/jobs/runs/submit",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": CONTENT_TYPE_JSON
                },
                json=payload,
                timeout=30
            )

            if resp.status_code == 200:
                run_id = str(resp.json()["run_id"])
                run_url = f"{host}/#job/runs/{run_id}"
                print(f"[OMD_SUBMIT] ✅ Run submitted, run_id={run_id}")
                return {"status": "success", "run_id": run_id, "run_url": run_url}
            else:
                print(f"[OMD_SUBMIT] ❌ Failed ({resp.status_code}): {resp.text}")
                return {"status": "error", "message": f"runs/submit failed ({resp.status_code}): {resp.text}"}

        except Exception as e:
            print(f"[OMD_SUBMIT] ❌ Exception: {e}")
            return {"status": "error", "message": str(e)}

    def get_run_status(self, run_id: str) -> Dict[str, Any]:
        """Get status of a job run"""
        if not self.client:
            return {
                'status': 'error',
                'message': 'Databricks client not initialized'
            }
        
        try:
            run = self.client.jobs.get_run(run_id=int(run_id))
            
            # Map Databricks state to our status
            state = run.state.life_cycle_state.value if run.state else 'UNKNOWN'
            result_state = run.state.result_state.value if run.state and run.state.result_state else None
            state_message = run.state.state_message if run.state and hasattr(run.state, 'state_message') else None
            
            status_mapping = {
                'PENDING': 'pending',
                'QUEUED': 'pending',
                'BLOCKED': 'pending',
                'RUNNING': 'running',
                'WAITING_FOR_RETRY': 'running',
                'TERMINATING': 'completed' if result_state == 'SUCCESS' else ('failed' if result_state else 'running'),
                'TERMINATED': 'completed' if result_state == 'SUCCESS' else 'failed',
                'SKIPPED': 'failed',
                'INTERNAL_ERROR': 'failed'
            }
            
            return {
                'status': status_mapping.get(state, 'unknown'),
                'databricks_state': state,
                'result_state': result_state,
                'state_message': state_message,
                'start_time': run.start_time,
                'end_time': run.end_time,
                'tasks': self._get_task_status(run)
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Failed to get run status: {str(e)}'
            }
    
    def _get_task_status(self, run) -> List[Dict[str, Any]]:
        """Extract task status from run"""
        tasks = []
        
        if hasattr(run, 'tasks') and run.tasks:
            for task in run.tasks:
                task_info = {
                    'task_key': task.task_key,
                    'state': task.state.life_cycle_state.value if task.state else 'UNKNOWN',
                    'result_state': task.state.result_state.value if task.state and task.state.result_state else None,
                    'start_time': task.start_time,
                    'end_time': task.end_time
                }
                tasks.append(task_info)
        
        return tasks
    
    @staticmethod
    def _task_passed(task) -> bool:
        return bool(task.state and task.state.result_state and task.state.result_state.value == 'SUCCESS')

    def _fetch_task_output(self, task):
        """Notebook output of a task run (only notebook tasks have one), or None when unavailable."""
        if not getattr(task, 'run_id', None):
            return None
        try:
            task_run_output = self.client.jobs.get_run_output(run_id=task.run_id)
            if hasattr(task_run_output, 'notebook_output'):
                return task_run_output.notebook_output.result
        except Exception as e:
            print(f"[GET_RUN_OUTPUT] Could not fetch output for task {task.task_key}: {e}")
        return None

    def get_run_output(self, run_id: str) -> Dict[str, Any]:
        """Get output/results from a completed job run"""
        print(f"[GET_RUN_OUTPUT] Fetching output for run {run_id}...")
        
        try:
            run = self.client.jobs.get_run(run_id=int(run_id))
            
            # Aggregate results from all tasks
            tasks = getattr(run, 'tasks', None) or []
            results = {
                'overall_status': 'completed',
                'tasks_total': len(tasks),
                'tasks_passed': 0,
                'tasks_failed': 0,
                'checks': [],
                'task_outputs': {}
            }
            
            for task in tasks:
                task_passed = self._task_passed(task)
                task_output = self._fetch_task_output(task)
                
                results['tasks_passed' if task_passed else 'tasks_failed'] += 1
                
                # Store task output if available
                if task_output:
                    results['task_outputs'][task.task_key] = task_output
                
                # Extract task results (would come from notebook output)
                results['checks'].append({
                    'task_key': task.task_key,
                    'status': 'passed' if task_passed else 'failed',
                    'score': None,  # Would be extracted from notebook output
                    'details': {},
                    'output': task_output  # Include output in result
                })
            
            # Calculate overall scores
            if results['tasks_total'] > 0:
                results['overall_score'] = f"{(results['tasks_passed'] / results['tasks_total']) * 100:.1f}%"
            else:
                results['overall_score'] = "N/A"
            
            return results
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Failed to get run output: {str(e)}'
            }
    
    def delete_job(self, job_id: str) -> Dict[str, Any]:
        """Delete a Databricks job"""
        print(f"[DELETE_JOB] Deleting job {job_id}...")
        
        try:
            self.client.jobs.delete(job_id=int(job_id))
            return {
                'status': 'success',
                'message': f'Job {job_id} deleted successfully'
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Failed to delete job: {str(e)}'
            }    
    def update_job_schedule(self, job_id: str, cron_expression: str, timezone: str = 'UTC', pause_status: str = 'UNPAUSED') -> Dict[str, Any]:
        """
        Update Databricks job schedule using cron expression
        
        Args:
            job_id: Databricks job ID
            cron_expression: Quartz cron expression (e.g., "0 0 * * *")
            timezone: Timezone for schedule (e.g., "UTC", "Europe/Paris")
            pause_status: PAUSED or UNPAUSED
            
        Returns:
            Dict with status and message
        """
        print(f"[UPDATE_JOB_SCHEDULE] Updating schedule for job {job_id}...")
        print(f"[UPDATE_JOB_SCHEDULE] Cron: {cron_expression}, Timezone: {timezone}")
        
        try:
            from databricks.sdk.service.jobs import CronSchedule, PauseStatus, JobSettings
            
            # Get current job configuration
            job = self.client.jobs.get(job_id=int(job_id))
            
            # Create new schedule
            new_schedule = CronSchedule(
                quartz_cron_expression=cron_expression,
                timezone_id=timezone,
                pause_status=PauseStatus[pause_status]
            )
            
            # Update job with new schedule (use JobSettings object, not dict)
            self.client.jobs.update(
                job_id=int(job_id),
                new_settings=JobSettings(
                    schedule=new_schedule
                )
            )
            
            print(f"[UPDATE_JOB_SCHEDULE] ✅ Schedule updated successfully")
            
            return {
                'status': 'success',
                'message': f'Job schedule updated successfully',
                'cron_expression': cron_expression,
                'timezone': timezone
            }
        except Exception as e:
            print(f"[UPDATE_JOB_SCHEDULE] ❌ Failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                'status': 'error',
                'message': f'Failed to update job schedule: {str(e)}'
            }
