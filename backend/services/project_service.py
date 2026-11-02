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
Project Service - Business logic for project operations
"""
import json
import logging
import os
import re
from typing import Dict, Any, List, Optional
from database.repositories import ProjectRepository, JobRepository
from databricks.sdk import WorkspaceClient

logger = logging.getLogger(__name__)

PROJECT_NOT_FOUND = "Project not found"


class ProjectService:
    def get_user_id_by_email(self, user_email: str) -> int:
        """
        Retourne l'user_id à partir de l'email (ou None si non trouvé)
        """
        from database.connection import get_db_connection, DB_CONFIG
        with get_db_connection() as conn:
            cursor = conn.cursor()
            full_users_table = f"{DB_CONFIG['schema']}.users"
            email_escaped = user_email.replace("'", "''")
            cursor.execute(f"SELECT id FROM {full_users_table} WHERE email = %s", (user_email,))
            result = cursor.fetchone()
            cursor.close()
            return result[0] if result else None

    def share_project(self, project_id: int, owner_user_id: int, target_user_email: str) -> Dict[str, Any]:
        """
        Partage un projet avec un utilisateur (par email)
        """
        # Empêcher le partage à soi-même
        target_user_id = self.get_user_id_by_email(target_user_email)
        if not target_user_id:
            return {"status": "error", "message": "Target user not found"}
        if owner_user_id == target_user_id:
            return {"status": "error", "message": "Cannot share the project with yourself"}
        # Check that the requester is the owner
        project = self.repository.get_project_by_id(project_id)
        if not project or project.get('user_id') != owner_user_id:
            return {"status": "error", "message": "Only the project owner can share this project"}
        # Check for duplicate
        if self.repository.user_has_access_to_project(project_id, target_user_id):
            return {"status": "error", "message": "This project is already shared with this user"}
        # Share
        success = self.repository.share_project_with_user(project_id, target_user_id)
        if success:
            return {"status": "success", "message": "Project shared successfully"}
        else:
            return {"status": "error", "message": "Error while sharing the project"}

    def unshare_project(self, project_id: int, owner_user_id: int, target_user_email: str) -> Dict[str, Any]:
        """
        Retire le partage d’un projet pour un utilisateur
        """
        target_user_id = self.get_user_id_by_email(target_user_email)
        if not target_user_id:
            return {"status": "error", "message": "Utilisateur cible introuvable"}
        # Vérifier que le demandeur est bien le propriétaire
        project = self.repository.get_project_by_id(project_id)
        if not project or project.get('user_id') != owner_user_id:
            return {"status": "error", "message": "Seul le propriétaire peut retirer le partage"}
        success = self.repository.unshare_project_with_user(project_id, target_user_id)
        if success:
            return {"status": "success", "message": "Partage retiré avec succès"}
        else:
            return {"status": "error", "message": "Erreur lors du retrait du partage"}

    def get_projects_shared_with_user(self, user_id: int) -> Dict[str, Any]:
        """
        Retourne tous les projets partagés avec un utilisateur
        """
        try:
            db_projects = self.repository.get_projects_shared_with_user(user_id)
            projects = []
            for proj in db_projects:
                config = self._parse_json_config(proj.get('config'))
                projects.append({
                    'id': proj.get('id'),
                    'name': proj.get('project_name'),
                    'description': proj.get('description', ''),
                    'status': proj.get('status', 'draft'),
                    'created_at': proj.get('created_at').isoformat() if proj.get('created_at') else None,
                    'last_modified': proj.get('updated_at').isoformat() if proj.get('updated_at') else None,
                    'step': proj.get('step', 1),
                    'config': config
                })
            return {"status": "success", "projects": projects, "total": len(projects)}
        except Exception as e:
            return {"status": "error", "message": f"Erreur lors de la récupération des projets partagés: {str(e)}", "projects": [], "total": 0}

    def user_has_access_to_project(self, project_id: int, user_id: int) -> bool:
        """
        Vérifie si un utilisateur a accès à un projet (propriétaire ou partagé)
        """
        return self.repository.user_has_access_to_project(project_id, user_id)
    """Service for project-related business logic"""
    
    def __init__(self):
        self.repository = ProjectRepository()
        self.job_repository = JobRepository()
    
    def create_project(self, user_email: str, project_name: str, description: str = "",
                      source_type: str = "unity_catalog", config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Create a new data quality project
        
        Args:
            user_email: User email address
            project_name: Name of the project
            description: Project description
            source_type: Type of data source
            config: Source configuration dictionary
            
        Returns:
            Dictionary with status and project ID
        """
        try:
            if config is None:
                config = {}
            project_id = self.repository.create_project(
                user_email, project_name, description, source_type, config
            )
            if project_id:
                # Return immediately - DBFS directory will be created lazily when needed
                # This significantly improves response time
                return {
                    "status": "success",
                    "project_id": project_id,
                    "message": "Project created successfully"
                }
            else:
                return {
                    "status": "error",
                    "message": "Failed to create project"
                }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to create project: {str(e)}"
            }
    
    def get_user_projects(self, user_email: str) -> Dict[str, Any]:
        """
        Get all projects for a user
        
        Args:
            user_email: User email address
            
        Returns:
            Dictionary with status and list of projects
        """
        try:
            db_projects = self.repository.get_user_projects(user_email)
            
            # Transform database format to frontend format
            projects = [self._build_project_entry(proj) for proj in db_projects]
            
            return {
                "status": "success",
                "projects": projects,
                "total": len(projects)
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to fetch projects: {str(e)}",
                "projects": [],
                "total": 0
            }
    
    @staticmethod
    def _parse_json_config(raw) -> Dict[str, Any]:
        """Return the project config as a dict (stored as a JSON string); {} when empty or invalid."""
        if not raw:
            return {}
        if not isinstance(raw, str):
            return raw
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse project config: {str(e)}")
            return {}

    @staticmethod
    def _compute_project_status(job_stats: Dict[str, int]) -> str:
        """Project status derived from its jobs: deployed, configured or draft."""
        total = job_stats['total']
        if total > 0 and job_stats['deployed'] == total:
            return 'deployed'
        if total > 0 and job_stats['deployed'] + job_stats['configured'] == total:
            return 'configured'
        return 'draft'

    def _get_shared_with(self, project_id: int) -> List[str]:
        """Emails of the users a project is shared with (empty list on failure)."""
        try:
            from database.connection import get_db_connection, DB_CONFIG
            with get_db_connection() as conn:
                cursor = conn.cursor()
                full_shares = f"{DB_CONFIG['schema']}.dq_project_shares"
                full_users = f"{DB_CONFIG['schema']}.users"
                cursor.execute(f"""
                    SELECT u.email FROM {full_shares} s
                    JOIN {full_users} u ON s.user_id = u.id
                    WHERE s.project_id = %s
                """, (project_id,))
                emails = [row[0] for row in cursor.fetchall()]
                cursor.close()
                return emails
        except Exception as e:
            logger.warning(f"Failed to fetch shared_with for project {project_id}: {e}")
            return []

    def _build_project_entry(self, proj: Dict[str, Any]) -> Dict[str, Any]:
        """Frontend representation of a project row, including job statistics and sharing."""
        project_id = proj.get('id')
        jobs = self.job_repository.get_jobs_by_project(project_id)
        job_stats = {
            'total': len(jobs),
            'deployed': sum(1 for j in jobs if j.get('status') == 'deployed'),
            'configured': sum(1 for j in jobs if j.get('status') in ['configured', 'active']),
            'draft': sum(1 for j in jobs if j.get('status') == 'draft')
        }
        created_at = proj.get('created_at')
        updated_at = proj.get('updated_at')
        return {
            'id': project_id,
            'name': proj.get('project_name'),
            'description': proj.get('description', ''),
            'status': self._compute_project_status(job_stats),
            'created_at': created_at.isoformat() if created_at else None,
            'last_modified': updated_at.isoformat() if updated_at else None,
            'step': proj.get('step', 1),
            'config': self._parse_json_config(proj.get('config')),
            'job_stats': job_stats,
            'shared_with': self._get_shared_with(project_id)
        }

    def get_project(self, project_id: int) -> Dict[str, Any]:
        """
        Get project by ID
        
        Args:
            project_id: Project ID
            
        Returns:
            Dictionary with status and project data
        """
        try:
            project = self.repository.get_project_by_id(project_id)
            
            if project:
                # Parse config from JSON string to dict
                if project.get('config'):
                    try:
                        if isinstance(project['config'], str):
                            project['config'] = json.loads(project['config'])
                    except json.JSONDecodeError as e:
                        print(f"Failed to parse project config: {str(e)}")
                        project['config'] = {}
                
                # Transform to frontend format
                formatted_project = {
                    'id': project.get('id'),
                    'name': project.get('project_name'),
                    'description': project.get('description', ''),
                    'status': project.get('status', 'draft'),
                    'created_at': project.get('created_at').isoformat() if project.get('created_at') else None,
                    'last_modified': project.get('updated_at').isoformat() if project.get('updated_at') else None,
                    'step': project.get('step', 1),
                    'config': project.get('config', {}),
                    'shared_with': project.get('shared_with', [])
                }
                return {
                    "status": "success",
                    "project": formatted_project
                }
            else:
                return {
                    "status": "error",
                    "message": PROJECT_NOT_FOUND
                }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to get project: {str(e)}"
            }
    
    def update_project(self, project_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update project
        
        Args:
            project_id: Project ID
            updates: Dictionary of fields to update
            
        Returns:
            Dictionary with status
        """
        try:
            success = self.repository.update_project(project_id, updates)
            
            if success:
                return {
                    "status": "success",
                    "message": "Project updated successfully"
                }
            else:
                return {
                    "status": "error",
                    "message": "Failed to update project"
                }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to update project: {str(e)}"
            }
    
    def delete_project(self, project_id: int) -> Dict[str, Any]:
        """
        Delete project with cascade deletion of all associated jobs
        
        Args:
            project_id: Project ID
            
        Returns:
            Dictionary with status
        """
        try:
            # First, get all jobs for this project
            jobs = self.job_repository.get_jobs_by_project(project_id)
            print(f"[DELETE PROJECT] Found {len(jobs)} jobs to delete for project {project_id}")
            
            # Delete all jobs first (cascade deletion)
            deleted_jobs = 0
            failed_jobs = []
            for job in jobs:
                job_id = job.get('id')
                try:
                    success = self.job_repository.delete_job(job_id)
                    if success:
                        deleted_jobs += 1
                        print(f"[DELETE PROJECT] Deleted job {job_id}")
                    else:
                        failed_jobs.append(job_id)
                        print(f"[DELETE PROJECT] Failed to delete job {job_id}")
                except Exception as job_error:
                    failed_jobs.append(job_id)
                    print(f"[DELETE PROJECT] Error deleting job {job_id}: {str(job_error)}")
            
            # If some jobs failed to delete, return error
            if failed_jobs:
                return {
                    "status": "error",
                    "message": f"Failed to delete {len(failed_jobs)} job(s). Cannot delete project. Job IDs: {failed_jobs}"
                }
            
            # Now delete the project
            success = self.repository.delete_project(project_id)
            
            if success:
                return {
                    "status": "success",
                    "message": f"Project deleted successfully (including {deleted_jobs} job(s))"
                }
            else:
                return {
                    "status": "error",
                    "message": "Failed to delete project after deleting jobs. Jobs were deleted but project remains."
                }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "message": f"Failed to delete project: {str(e)}"
            }
    
    def duplicate_project(self, project_id: int, user_email: str) -> Dict[str, Any]:
        """
        Duplicate an existing project
        
        Args:
            project_id: Project ID to duplicate
            user_email: Email of user creating the duplicate
            
        Returns:
            Dictionary with status and new project information
        """
        try:
            # Get the original project
            original_project = self.repository.get_project_by_id(project_id)
            
            if not original_project:
                return {
                    "status": "error",
                    "message": PROJECT_NOT_FOUND
                }
            
            # Parse the source config
            config = self._parse_json_config(original_project.get('config'))
            
            # Create duplicate with modified name
            original_name = original_project.get('project_name', 'Project')
            new_name = f"{original_name} (Copy)"
            
            new_project_id = self.repository.create_project(
                user_email=user_email,
                project_name=new_name,
                description=original_project.get('description', ''),
                source_type=original_project.get('source_type', 'unity_catalog'),
                config=config
            )
            
            if new_project_id:
                return {
                    "status": "success",
                    "project_id": new_project_id,
                    "message": "Project duplicated successfully"
                }
            else:
                return {
                    "status": "error",
                    "message": "Failed to create duplicate project"
                }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to duplicate project: {str(e)}"
            }    
    @staticmethod
    def _find_warehouse_id(w) -> Optional[str]:
        """Id of a running SQL warehouse, else the first available one (None when unavailable)."""
        try:
            warehouses = list(w.warehouses.list())
        except Exception as e:
            logger.warning(f"Error listing warehouses: {str(e)}")
            return None
        running = next((wh for wh in warehouses if wh.state and str(wh.state).upper() == 'RUNNING'), None)
        chosen = running or (warehouses[0] if warehouses else None)
        return chosen.id if chosen else None

    @staticmethod
    def _safe_query_rows(label: str, w, warehouse_id: str, catalog: str, results_schema: str,
                         query: str) -> List[Dict[str, Any]]:
        """Run a SQL statement and return its rows as dicts; logs and returns [] on failure."""
        try:
            logger.debug(f"Querying {label}: {query}")
            result = w.statement_execution.execute_statement(
                warehouse_id=warehouse_id,
                statement=query,
                catalog=catalog,
                schema=results_schema
            )
            if not (result.result and result.result.data_array):
                logger.debug(f"No data in {label}")
                return []
            columns = [col.name for col in result.manifest.schema.columns]
            return [dict(zip(columns, row)) for row in result.result.data_array]
        except Exception as e:
            logger.error(f"Could not fetch {label}: {str(e)}", exc_info=True)
            return []

    def get_last_run_report(self, project_id: int) -> Dict[str, Any]:
        """
        Get the last run report data for a project
        Fetches data from aggregate checks, column summary, and dataset summary tables
        
        Args:
            project_id: Project ID
            
        Returns:
            Dictionary with status and report data
        """
        try:
            # Get project to verify it exists
            project = self.repository.get_project_by_id(project_id)
            if not project:
                return {
                    "status": "error",
                    "message": PROJECT_NOT_FOUND
                }
            
            # Get the most recent job for this project
            jobs = self.job_repository.get_jobs_by_project(project_id)
            if not jobs:
                return {
                    "status": "error",
                    "message": "No job found for this project"
                }
            
            # Get the most recent job (first in list, assuming ordered by created_at desc)
            job = jobs[0]
            job_name = job.get('job_name', '')
            
            # Sanitize names for table naming
            def sanitize_name(name):
                return re.sub(r'[^a-zA-Z0-9_]', '_', name).lower()
            
            project_name = project.get('project_name', '')
            project_name_clean = sanitize_name(project_name) if project_name else f"project_{project_id}"
            job_name_clean = sanitize_name(job_name) if job_name else f"job_{job.get('id')}"
            
            # Get catalog and schema from job config or use defaults
            config = self._parse_json_config(job.get('job_config', {}))
            
            catalog = config.get('catalog') or os.getenv('UC_CATALOG', '')
            results_schema = config.get('results_schema') or os.getenv('UC_RESULTS_SCHEMA', 'db_gdm_dq_results')
            
            logger.debug(f"Catalog: {catalog}, Schema: {results_schema}")
            logger.debug(f"Project name clean: {project_name_clean}, Job name clean: {job_name_clean}")
            
            # Get SQL warehouse for remote queries
            w = WorkspaceClient()
            warehouse_id = self._find_warehouse_id(w)
            
            if not warehouse_id:
                return {
                    "status": "error",
                    "message": "No SQL warehouse available for queries"
                }
            
            # Table names: always combine project + job (raw names stored in DB)
            aggregate_table = f"{catalog}.{results_schema}.dq_{project_name_clean}_{job_name_clean}_checks_aggregated"
            column_summary_table = f"{catalog}.{results_schema}.dq_{project_name_clean}_{job_name_clean}_summary_columns"
            dataset_summary_table = f"{catalog}.{results_schema}.dq_{project_name_clean}_{job_name_clean}_summary_dataset"
            faulty_records_table = f"{catalog}.{results_schema}.dq_{project_name_clean}_{job_name_clean}_faulty_records"
            
            # Initialize report data structure
            report_data = {
                "project_name": project_name,
                "job_name": job_name,
                "job_id": job.get('id'),
                "databricks_job_id": job.get('databricks_job_id'),
                "aggregate_checks": [],
                "column_summary": [],
                "dataset_summary": [],
                "faulty_records_count": 0,
                "faulty_records_table": faulty_records_table,
                "execution_timestamp": None
            }
            
            # Query column summary (most important for KPIs)
            column_rows = self._safe_query_rows(
                "column summary", w, warehouse_id, catalog, results_schema,
                f"SELECT * FROM {column_summary_table} ORDER BY execution_timestamp DESC LIMIT 1000"
            )
            report_data['column_summary'] = column_rows
            report_data['execution_timestamp'] = next(
                (row['execution_timestamp'] for row in column_rows if row.get('execution_timestamp')), None
            )

            # Query dataset summary
            report_data['dataset_summary'] = self._safe_query_rows(
                "dataset summary", w, warehouse_id, catalog, results_schema,
                f"SELECT * FROM {dataset_summary_table} ORDER BY execution_timestamp DESC"
            )

            # Get faulty records count
            count_rows = self._safe_query_rows(
                "faulty records count", w, warehouse_id, catalog, results_schema,
                f"SELECT COUNT(*) as count FROM {faulty_records_table}"
            )
            if count_rows:
                report_data['faulty_records_count'] = next(iter(count_rows[0].values()))
            
            logger.debug(
                f"Final report data summary - Column rows: {len(report_data['column_summary'])}, "
                f"Dataset rows: {len(report_data['dataset_summary'])}"
            )
            
            return {
                "status": "success",
                "report": report_data
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to fetch report: {str(e)}"
            }

    # download_faulty_records has been moved to JobService.
    # Use GET /api/dq/jobs/{job_id}/faulty-records/download instead.
