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
Databricks Job Deployment Service
Handles notebook generation, upload, and job creation for DQ workflows
"""
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs, compute
from typing import Dict, List, Any
import json
import logging
from config.settings import Settings

logger = logging.getLogger(__name__)


class DatabricksDeploymentService:
    """Manages Databricks job deployment with dynamic notebook generation"""
    
    def __init__(self):
        """Initialize service (client created on first use)"""
        self._client = None
        self.host = ''
        self.settings = Settings()
        logger.info("DatabricksDeploymentService initialized")
    
    @property
    def client(self):
        """Lazy initialization of Databricks client"""
        if self._client is None:
            import os
            import sys
            
            try:
                logger.info("Creating WorkspaceClient via Service Principal...")
                print("Creating WorkspaceClient...", file=sys.stderr)
                
                from config.databricks_auth import get_workspace_client, get_host
                self._client = get_workspace_client()
                self.host = get_host()
                
                logger.info(f"WorkspaceClient created successfully, host: {self.host}")
                print(f"WorkspaceClient created, host: {self.host}", file=sys.stderr)
                
            except Exception as e:
                error_msg = f"Failed to create WorkspaceClient: {e}"
                logger.error(error_msg, exc_info=True)
                print(f"ERROR: {error_msg}", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)
                raise RuntimeError(error_msg) from e
        
        return self._client
    
    @staticmethod
    def _resolve_source_path(project_config: Dict[str, Any]) -> str:
        """Extract source path, checking top-level key then nested files[0]['volume_path']."""
        source_path = project_config.get('source_path', '')
        if not source_path and project_config.get('source_type', 'csv') == 'csv':
            files = project_config.get('files', [])
            if files:
                source_path = files[0].get('volume_path', '')
        if not source_path:
            logger.warning("source_path is empty in project_config")
        return source_path

    @staticmethod
    def _get_dimension_from_component(comp) -> str:
        """Return the dimension name for a component (str or dict), or '' for unknown types."""
        if isinstance(comp, str):
            comp_id = comp
        elif isinstance(comp, dict):
            comp_id = comp.get('id', '')
        else:
            return ''
        comp_lower = comp_id.lower()
        if 'completeness' in comp_lower:
            return 'completeness'
        if 'validity' in comp_lower:
            return 'validity'
        if 'uniqueness' in comp_lower:
            return 'uniqueness'
        if 'consistency' in comp_lower:
            return 'consistency'
        if 'accuracy' in comp_lower:
            return 'accuracy'
        return ''

    def deploy_dq_job(self, project_id: int, project_config: Dict[str, Any],
                     enabled_components: List[Dict[str, Any]],
                     deployment_config: Dict[str, Any],
                     user_email: str = None):
        """
        Deploy complete DQ job with notebooks and tasks
        Generator that yields status updates during deployment

        Args:
            project_id: Project ID
            project_config: Project configuration (source, columns, etc.)
            enabled_components: List of enabled DQ components
            deployment_config: Job deployment configuration
            user_email: User's email to set as job owner (optional)

        Yields:
            Dict with status updates: {'step': str, 'status': str, 'message': str}
        """
        if not self.client:
            yield {'step': 'initialization', 'status': 'error', 'message': 'Databricks client not initialized'}
            return

        try:
            yield {'step': 'initialization', 'status': 'running', 'message': 'Starting deployment...'}
            logger.info(f"Deploying DQ job for project {project_id}")

            if isinstance(project_config, str):
                project_config = json.loads(project_config)

            # Extract configuration
            catalog = self.settings.uc_catalog
            schema = self.settings.uc_schema
            results_schema = self.settings.uc_results_schema
            source_type = project_config.get('source_type', 'csv')
            source_path = self._resolve_source_path(project_config)

            project_name = project_config.get('project_name', f'project_{project_id}')
            job_name = deployment_config.get('job_name', f'job_{project_id}')

            logger.info(f"Project: {project_name}, Job: {job_name}")
            logger.info(f"Results will be stored in: {catalog}.{results_schema}")

            yield {'step': 'initialization', 'status': 'success', 'message': 'Configuration validated'}

            # Get thresholds from deployment config
            threshold_ok = deployment_config.get('threshold_ok', 100.0)
            threshold_warning = deployment_config.get('threshold_warning', 98.0)
            thresholds_config = deployment_config.get('thresholds', {})
            extra_empty_values = project_config.get('extra_empty_values', [])
            component_configs = deployment_config.get('component_configs', {})

            # Determine enabled dimensions (deduplicated)
            logger.info(f"Processing {len(enabled_components)} enabled components...")
            enabled_dimensions = list({
                dim
                for comp in enabled_components
                for dim in [self._get_dimension_from_component(comp)]
                if dim
            })
            logger.info(f"Final enabled dimensions: {enabled_dimensions}")
            
            if not enabled_dimensions:
                error_msg = f"No valid dimensions detected from components: {enabled_components}"
                logger.error(error_msg)
                yield {'step': 'initialization', 'status': 'error', 'message': error_msg}
                return
            
            # Use static notebooks from Git Repos
            workspace_path = "/Workspace/Shared/notebooks"
            notebooks = self._get_notebook_paths(workspace_path)
            
            yield {'step': 'notebooks', 'status': 'success', 'message': f'Found {len(notebooks)} notebooks'}
            
            # Build task definitions with parameters
            yield {'step': 'tasks', 'status': 'running', 'message': 'Building task definitions...'}
            tasks = self._build_task_definitions_with_params(
                notebooks, enabled_dimensions, project_id, catalog, schema,
                results_schema, project_name, job_name,
                source_type, source_path, threshold_ok, 
                threshold_warning, extra_empty_values, component_configs,
                thresholds_config
            )
            
            yield {'step': 'tasks', 'status': 'success', 'message': f'Created {len(tasks)} tasks'}
            
            # Create Databricks job with format: {project_name}_{job_name}
            job_name_raw = deployment_config.get('job_name', f"job_{project_id}")
            databricks_job_name = f"{project_name}_{job_name_raw}"
            logger.info(f"Creating Databricks job: {databricks_job_name} (project: {project_name}, job: {job_name_raw})")
            
            yield {'step': 'job_creation', 'status': 'running', 'message': f'Creating job: {databricks_job_name}'}
            
            # Use generator version for task-by-task updates
            for update in self._create_databricks_job_with_updates(databricks_job_name, tasks, deployment_config, user_email):
                yield update
                if update.get('status') == 'error':
                    return
            
            # Get final result from last update
            if update.get('job_id'):
                job_result = update
                logger.info(f"Databricks job created successfully: {job_result['job_id']}")
                
                yield {
                    'step': 'complete',
                    'status': 'success',
                    'message': f'Successfully deployed job with {len(tasks)} tasks',
                    'job_id': job_result['job_id'],
                    'job_url': job_result['job_url'],
                    'workspace_path': workspace_path,
                    'databricks_job_name': databricks_job_name,
                    'tasks': tasks,
                    'notebooks': notebooks
                }
            else:
                raise Exception("Failed to create Databricks job - no job_id returned")
            
        except Exception as e:
            logger.error(f"ERROR in deploy_dq_job: {str(e)}", exc_info=True)
            yield {
                'step': 'error',
                'status': 'error',
                'message': f'Deployment failed: {str(e)}'
            }
    
    def _get_notebook_paths(self, workspace_path: str) -> List[Dict[str, str]]:
        """Get paths to static notebooks in the Git repo"""
        notebook_names = [
            'prepare_input',
            'completeness_check',
            'uniqueness_check',
            'validity_check',
            'meaning_validity_check',
            'consistency_check',
            'accuracy_check',
            'aggregate_checks',
            'generate_column_summary',
            'generate_dataset_summary',
            'extract_faulty_records'
        ]
        
        return [
            {'name': name, 'path': f"{workspace_path}/{name}"}
            for name in notebook_names
        ]
    
    def _build_task_definitions_with_params(self, notebooks: List[Dict], enabled_dimensions: List[str],
                                           project_id: int, catalog: str, schema: str,
                                           results_schema: str, project_name: str, job_name: str,
                                           source_type: str, source_path: str,
                                           threshold_ok: float, threshold_warning: float,
                                           extra_empty_values: List[str],
                                           component_configs: Dict[str, Any],
                                           thresholds_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build Databricks task definitions with parameters"""
        thresholds_json = self._build_thresholds_json(
            component_configs, thresholds_config, threshold_ok, threshold_warning
        )
        notebook_paths = {nb['name']: nb['path'] for nb in notebooks}
        tasks: List[Dict[str, Any]] = []

        def add_task(suffix: str, task_name: str, notebook: str, depends_on: List[str],
                     parameters: Dict[str, Any]) -> str:
            task_key = f'task_{len(tasks)}_{suffix}'
            tasks.append({
                'task_key': task_key,
                'task_name': task_name,
                'notebook_path': notebook_paths[notebook],
                'depends_on': depends_on,
                'parameters': parameters
            })
            return task_key

        # Common parameters for all tasks
        common_params = {
            "project_id": str(project_id),
            "project_name": project_name,
            "job_name": job_name,
            "catalog": catalog,
            "schema": schema,
            "results_schema": results_schema
        }

        # Task 0: Prepare Input (processes ALL columns from source automatically)
        prepare_task_key = add_task(
            'prepare_input', 'Prepare Input Data', 'prepare_input', [],
            {**common_params, "source_type": source_type, "source_path": source_path}
        )

        # Check tasks (parallel, all depend on prepare)
        check_tasks = [
            add_task(suffix, task_name, notebook, [prepare_task_key], parameters)
            for suffix, task_name, notebook, parameters
            in self._build_check_specs(enabled_dimensions, component_configs, common_params)
        ]
        logger.info(f"[TASK BUILD] Total check tasks created: {len(check_tasks)} from dimensions: {enabled_dimensions}")

        # Aggregate checks (depends on all check tasks)
        dimensions_json = json.dumps(enabled_dimensions)
        aggregate_task_key = add_task(
            'aggregate', 'Aggregate Checks', 'aggregate_checks', check_tasks or [prepare_task_key],
            {**common_params, "enabled_dimensions": dimensions_json}
        )

        # Column summary (depends on aggregate), then dataset summary (depends on column summary)
        summary_params = {
            **common_params,
            "enabled_dimensions": dimensions_json,
            "threshold_ok": str(threshold_ok),
            "threshold_warning": str(threshold_warning),
            "thresholds_json": thresholds_json
        }
        column_summary_task_key = add_task(
            'column_summary', 'Generate Column Summary', 'generate_column_summary',
            [aggregate_task_key], summary_params
        )
        add_task(
            'dataset_summary', 'Generate Dataset Summary', 'generate_dataset_summary',
            [column_summary_task_key], dict(summary_params)
        )

        # Faulty records (depends on aggregate, runs in parallel with summaries)
        add_task('faulty_records', 'Extract Faulty Records', 'extract_faulty_records', [aggregate_task_key], common_params)

        return tasks

    # Maps component_id (as stored in session state) to the dimension name used by notebooks
    _COMPONENT_TO_DIMENSION: Dict[str, str] = {
        'completeness': 'completeness',
        'uniqueness': 'uniqueness',
        'consistency': 'consistency',
        'validity_numeric': 'validity',
        'validity_date': 'validity',
        'meaning_validity': 'validity',
        'accuracy_custom_rules': 'accuracy',
    }

    @staticmethod
    def _build_thresholds_json(component_configs: Dict, thresholds_config: Dict,
                               threshold_ok: float, threshold_warning: float) -> str:
        """Build a JSON string of merged threshold configurations for downstream notebooks.

        Notebooks read thresholds via::

            THRESHOLDS_CONFIG["by_dimension"][dimension][column_name]

        so we must convert the session-state structure
        ``{component_id: {column: {ok, warning}}}``
        into ``{"by_dimension": {dimension: {column: {ok, warning}}}}``.
        """
        thresholds: Dict[str, Any] = {
            'threshold_ok': threshold_ok,
            'threshold_warning': threshold_warning,
        }
        if thresholds_config:
            by_dimension: Dict[str, Any] = {}
            for comp_id, col_thresholds in thresholds_config.items():
                if not isinstance(col_thresholds, dict):
                    continue
                dim = DatabricksDeploymentService._COMPONENT_TO_DIMENSION.get(comp_id, comp_id)
                by_dimension.setdefault(dim, {}).update(col_thresholds)
            if by_dimension:
                thresholds['by_dimension'] = by_dimension
        return json.dumps(thresholds)

    def _build_check_specs(self, enabled_dimensions: List[str],
                           component_configs: Dict, common_params: Dict):
        """Yield (suffix, task_name, notebook, parameters) for each enabled check dimension."""
        _BUILDERS = {
            'completeness': DatabricksDeploymentService._completeness_spec,
            'uniqueness':   DatabricksDeploymentService._uniqueness_spec,
            'consistency':  DatabricksDeploymentService._consistency_spec,
            'validity':     DatabricksDeploymentService._validity_spec,
            'accuracy':     DatabricksDeploymentService._accuracy_spec,
        }
        for dim in enabled_dimensions:
            builder = _BUILDERS.get(dim)
            if builder is None:
                logger.warning(f"[TASK BUILD] Unknown dimension '{dim}' — using common params only")
                yield (dim, f"{dim.capitalize()} Check", f"{dim}_check", common_params)
                continue
            spec = builder(component_configs, common_params)
            if spec is not None:
                yield spec

    @staticmethod
    def _completeness_spec(component_configs: Dict, common_params: Dict):
        """Build task spec for the completeness check."""
        cfg = component_configs.get('completeness', {})
        key_columns = cfg.get('key_columns', [])
        null_values_str = cfg.get('null_values', '')
        extra_empty = [v.strip() for v in null_values_str.split(',') if v.strip()] if null_values_str else []
        logger.info(f"[TASK BUILD] Completeness — columns: {key_columns}, extra_empty: {extra_empty}")
        return ('completeness', 'Completeness Check', 'completeness_check',
                {**common_params,
                 "columns": json.dumps(key_columns),
                 "extra_empty_values": json.dumps(extra_empty)})

    @staticmethod
    def _uniqueness_spec(component_configs: Dict, common_params: Dict):
        """Build task spec for the uniqueness check."""
        cfg = component_configs.get('uniqueness', {})
        key_columns = cfg.get('key_columns', [])
        check_mode = cfg.get('check_mode', 'Exact Match')
        logger.info(f"[TASK BUILD] Uniqueness — columns: {key_columns}, mode: {check_mode}")
        return ('uniqueness', 'Uniqueness Check', 'uniqueness_check',
                {**common_params,
                 "columns": json.dumps(key_columns),
                 "check_mode": check_mode,
                 "fuzzy_sensitivity": str(cfg.get('fuzzy_sensitivity', 80))})

    @staticmethod
    def _consistency_spec(component_configs: Dict, common_params: Dict):
        """Build task spec for the consistency check."""
        cfg = component_configs.get('consistency', {})
        column_a = cfg.get('column_a', '')
        column_b = cfg.get('column_b', '')
        check_mode = cfg.get('check_mode', 'Exact Match')
        logger.info(f"[TASK BUILD] Consistency — column_a: {column_a}, column_b: {column_b}, mode: {check_mode}")
        return ('consistency', 'Consistency Check', 'consistency_check',
                {**common_params,
                 "key_columns": json.dumps(cfg.get('key_columns', [])),
                 "column_a": column_a,
                 "column_b": column_b,
                 "check_mode": check_mode})

    @staticmethod
    def _validity_spec(component_configs: Dict, common_params: Dict):
        """Build task spec for the validity check (meaning, date, or numeric variant).

        meaning_validity and validity_numeric/date all share the 'validity' dimension
        and write to the same _validity table — detect which component is configured.
        """
        if 'meaning_validity' in component_configs:
            cfg = component_configs.get('meaning_validity', {})
            column_types = cfg.get('column_types', {})
            logger.info(f"[TASK BUILD] Validity (meaning) — column_types: {list(column_types.keys())}")
            return ('validity', 'Validity Check', 'meaning_validity_check',
                    {**common_params, "column_types": json.dumps(column_types)})
        if 'validity_date' in component_configs:
            cfg = component_configs.get('validity_date', {})
            logger.info(f"[TASK BUILD] Validity (date) — col1: {cfg.get('date_column_1')}, col2: {cfg.get('date_column_2')}")
            return ('validity', 'Validity Check', 'validity_check',
                    {**common_params,
                     "column_1": cfg.get('date_column_1', ''),
                     "column_2": cfg.get('date_column_2', ''),
                     "operator": cfg.get('operator', '>'),
                     "check_type": 'date'})
        cfg = component_configs.get('validity_numeric', {})
        logger.info(f"[TASK BUILD] Validity (numeric) — col1: {cfg.get('column_1')}, col2: {cfg.get('column_2')}")
        return ('validity', 'Validity Check', 'validity_check',
                {**common_params,
                 "column_1": cfg.get('column_1', ''),
                 "column_2": cfg.get('column_2', ''),
                 "operator": cfg.get('operator', '>'),
                 "check_type": 'numeric'})

    @staticmethod
    def _accuracy_spec(component_configs: Dict, common_params: Dict):
        """Build task spec for the accuracy check, or None if no rules are configured."""
        custom_rules = component_configs.get('accuracy_custom_rules', {}).get('custom_rules', [])
        if not custom_rules:
            logger.warning("[TASK BUILD] Accuracy check — no custom rules configured, skipping task")
            return None
        return ('accuracy', 'Accuracy Check', 'accuracy_check',
                {**common_params, "custom_rules_json": json.dumps(custom_rules)})

    def _create_databricks_job_with_updates(self, job_name: str, tasks: List[Dict],
                                            deployment_config: Dict, user_email: str = None):
        """
        Create Databricks job with task definitions using REST API
        Generator that yields updates for each task being added
        """
        import requests
        
        logger.info(f"[JOB CREATE] Starting job creation for '{job_name}' with {len(tasks)} tasks")
        
        # Yield initial status
        yield {'step': 'job_creation', 'status': 'running', 'message': f'Creating job: {job_name}'}

        # Get token and host via Service Principal
        try:
            from config.databricks_auth import get_access_token, get_host
            pat = get_access_token()
            host = get_host()
        except Exception as e:
            logger.error(f"[JOB CREATE] Could not obtain SP token: {e}")
            yield {'step': 'job_creation', 'status': 'error', 'message': f'Authentication failed: {e}'}
            return
        
        if not pat or not host:
            yield {'step': 'job_creation', 'status': 'error', 'message': 'No Databricks authentication token available'}
            return

        headers = {
            "Authorization": f"Bearer {pat}",
            "Content-Type": "application/json"
        }

        # Serverless compute — no cluster needed
        environment_key = 'default'

        api_tasks = []
        for idx, task in enumerate(tasks):
            task_name = task.get('task_name', task['task_key'])
            yield {
                'step': f'task_{idx}',
                'status': 'running',
                'message': f'Adding task: {task_name}',
                'task_key': task['task_key'],
                'task_name': task_name
            }
            
            logger.info(f"[API CONVERT] Processing task: {task['task_key']}")
            api_tasks.append(self._to_api_task(task, environment_key))

            yield {
                'step': f'task_{idx}',
                'status': 'success',
                'message': f'Task configured: {task_name}',
                'task_key': task['task_key'],
                'task_name': task_name
            }

        job_payload = self._build_job_payload(job_name, api_tasks, environment_key, deployment_config, user_email)

        yield {'step': 'job_submission', 'status': 'running', 'message': 'Submitting job to Databricks...'}
        
        url = f"https://{host}/api/2.1/jobs/create"
        logger.info(f"[JOB CREATE] POST {url}")
        response = requests.post(url, headers=headers, json=job_payload)
        logger.info(f"[JOB CREATE] Status: {response.status_code}")
        
        if response.status_code != 200:
            error_msg = f"Failed to create Databricks job: {response.text}"
            logger.error(error_msg)
            yield {'step': 'job_submission', 'status': 'error', 'message': error_msg}
            return
            
        data = response.json()
        job_id = data.get("job_id")
        if not job_id:
            error_msg = f"No job_id returned: {data}"
            logger.error(error_msg)
            yield {'step': 'job_submission', 'status': 'error', 'message': error_msg}
            return
            
        job_url = f"https://{host}/#job/{job_id}"
        
        logger.info(f"[JOB CREATE] ✅ Job created successfully: {job_id}")
        yield {'step': 'job_submission', 'status': 'success', 'message': f'Job created: {job_id}'}
        
        # Update job permissions to add session user as manager
        if user_email:
            yield {'step': 'permissions', 'status': 'running', 'message': f'Setting permissions for {user_email}'}
            if self._grant_manage_permission(host, headers, job_id, user_email):
                yield {'step': 'permissions', 'status': 'success', 'message': f'Permissions granted to {user_email}'}
            else:
                yield {'step': 'permissions', 'status': 'warning', 'message': 'Could not set permissions'}
        
        # Yield final success with job details
        yield {
            'step': 'job_creation',
            'status': 'success',
            'message': f'Job created successfully',
            'job_id': str(job_id),
            'job_url': job_url
        }
    
    @staticmethod
    def _to_api_task(task: Dict[str, Any], environment_key: str) -> Dict[str, Any]:
        """Convert an internal task definition to a Jobs API notebook task."""
        notebook_task = {"notebook_path": task["notebook_path"]}
        base_parameters = task.get("parameters", {})
        if base_parameters:
            notebook_task["base_parameters"] = base_parameters

        api_task = {
            "task_key": task["task_key"],
            "environment_key": environment_key,
            "notebook_task": notebook_task,
            "timeout_seconds": 3600
        }
        depends_on = task.get("depends_on")
        if depends_on:
            api_task["depends_on"] = [{"task_key": dep} for dep in depends_on if dep]
        return api_task

    @staticmethod
    def _build_job_payload(job_name: str, api_tasks: List[Dict[str, Any]], environment_key: str,
                           deployment_config: Dict[str, Any], user_email: str = None) -> Dict[str, Any]:
        """Jobs API payload: serverless environment, one concurrent run, failure e-mail if configured.

        When *user_email* is provided the job is configured with ``run_as`` so that
        all notebook tasks execute under the submitting user's identity.  This means
        Unity Catalog access is gated by that user's own privileges — if they can
        read/write the catalog they can run the job; if not, they get an explicit
        permission error rather than a cryptic service-principal failure.
        """
        job_payload = {
            "name": job_name,
            "environments": [{
                "environment_key": environment_key,
                "spec": {"client": "1"},
            }],
            "tasks": api_tasks,
            "max_concurrent_runs": 1,
            "timeout_seconds": 7200
        }
        if user_email:
            job_payload["run_as"] = {"user_name": user_email}
            logger.info(f"[JOB PAYLOAD] run_as set to user: {user_email}")
        if deployment_config.get("notification_email"):
            job_payload["email_notifications"] = {
                "on_failure": [deployment_config["notification_email"]]
            }
        return job_payload

    @staticmethod
    def _grant_manage_permission(host: str, headers: Dict[str, str], job_id, user_email: str) -> bool:
        """Grant the user CAN_MANAGE on the job; returns False (and logs) when it could not be set."""
        import requests
        try:
            logger.info(f"[JOB PERMISSIONS] Setting {user_email} as CAN_MANAGE for job {job_id}")
            permissions_payload = {
                "access_control_list": [
                    {"user_name": user_email, "permission_level": "CAN_MANAGE"}
                ]
            }
            perm_response = requests.patch(
                f"https://{host}/api/2.0/permissions/jobs/{job_id}", headers=headers, json=permissions_payload
            )
            if perm_response.status_code == 200:
                logger.info(f"[JOB PERMISSIONS] ✅ Successfully granted CAN_MANAGE to {user_email}")
                return True
            logger.error(f"[JOB PERMISSIONS] ⚠️ Failed to update permissions (status {perm_response.status_code}): {perm_response.text}")
        except Exception as e:
            logger.error(f"[JOB PERMISSIONS] ⚠️ Error updating job permissions: {e}", exc_info=True)
        return False
