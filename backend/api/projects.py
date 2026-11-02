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
Project API Endpoints
All project-related routes
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging
import traceback
from services import ProjectService, JobService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dq/projects", tags=["projects"])

PROJECT_NOT_FOUND = "Project not found"
project_service = ProjectService()
job_service = JobService()




@router.post("/create")
async def create_project(project_data: Dict[str, Any]):
    """Create a new data quality project"""
    try:
        _safe_name = str(project_data.get('project_name', '')).replace('\n', '_').replace('\r', '_')
        _safe_user = str(project_data.get('user_email', '')).replace('\n', '_').replace('\r', '_')
        logger.info("Creating project '%s' for user: %s", _safe_name, _safe_user)
        result = project_service.create_project(
            user_email=project_data.get('user_email'),
            project_name=project_data.get('project_name'),
            description=project_data.get('description', ''),
            source_type=project_data.get('source_type', 'unity_catalog'),
            config=project_data.get('config', {})
        )
        
        if result.get("status") == "success":
            return result
        else:
            error_msg = result.get("message", "Failed to create project")
            logger.error(f"Project creation failed: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating project: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to create project: {str(e)}")


@router.get("/user/{user_email}")
async def get_user_projects(user_email: str):
    """Get all projects for a user"""
    result = project_service.get_user_projects(user_email)
    
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to fetch projects"))


@router.get("/{project_id}")
async def get_project(project_id: int):
    """Get a single project by ID"""
    result = project_service.get_project(project_id)
    
    if result.get("status") == "success":
        return result
    elif result.get("message") == PROJECT_NOT_FOUND:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND)
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to fetch project"))


@router.delete("/{project_id}")
def delete_project(project_id: int):
    """Delete a data quality project"""
    result = project_service.delete_project(project_id)
    
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to delete project"))


@router.post("/{project_id}/duplicate")
def duplicate_project(project_id: int, duplicate_data: Dict[str, Any]):
    """Duplicate a data quality project"""
    user_email = duplicate_data.get('user_email')
    if not user_email:
        raise HTTPException(status_code=400, detail="user_email is required")
    
    result = project_service.duplicate_project(project_id, user_email)
    
    if result.get("status") == "success":
        return result
    elif result.get("message") == PROJECT_NOT_FOUND:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND)
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to duplicate project"))


@router.put("/{project_id}")
async def update_project(project_id: int, update_data: Dict[str, Any]):
    """Update a data quality project"""
    result = project_service.update_project(project_id, update_data)
    
    if result.get("status") == "success":
        return result
    elif result.get("message") == PROJECT_NOT_FOUND:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND)
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to update project"))


@router.get("/{project_id}/last-run-report")
async def get_last_run_report(project_id: int):
    """Get the last run report data for a project including DQ metrics and faulty records"""
    result = project_service.get_last_run_report(project_id)
    
    if result.get("status") == "success":
        return result
    elif result.get("message") == PROJECT_NOT_FOUND:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND)
    elif result.get("message") == "No job found for this project":
        raise HTTPException(status_code=404, detail="No job found for this project")
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to fetch report"))


@router.get("/{project_id}/jobs")
async def get_project_jobs(project_id: int):
    """Get all jobs for a project (3-layer architecture)"""
    result = job_service.get_jobs_by_project(project_id)
    
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to fetch jobs"))


@router.post("/{project_id}/jobs")
async def create_project_job(project_id: int, job_data: Dict[str, Any]):
    """Create a new job for a project (3-layer architecture)"""
    result = job_service.create_new_job(project_id, job_data)
    
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to create job"))



@router.post("/{project_id}/share")
async def share_project(project_id: int, data: Dict[str, Any]):
    """
    Partager un projet avec un utilisateur (par email)
    data attend : { "owner_user_id": int, "target_user_email": str }
    """
    owner_user_id = data.get("owner_user_id")
    target_user_email = data.get("target_user_email")
    if not owner_user_id or not target_user_email:
        raise HTTPException(status_code=400, detail="owner_user_id et target_user_email sont requis")
    result = project_service.share_project(project_id, owner_user_id, target_user_email)
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=400, detail=result.get("message", "Erreur lors du partage"))

@router.post("/{project_id}/unshare")
async def unshare_project(project_id: int, data: Dict[str, Any]):
    """
    Retirer le partage d’un projet pour un utilisateur (par email)
    data attend : { "owner_user_id": int, "target_user_email": str }
    """
    owner_user_id = data.get("owner_user_id")
    target_user_email = data.get("target_user_email")
    if not owner_user_id or not target_user_email:
        raise HTTPException(status_code=400, detail="owner_user_id et target_user_email sont requis")
    result = project_service.unshare_project(project_id, owner_user_id, target_user_email)
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=400, detail=result.get("message", "Erreur lors du retrait du partage"))

@router.get("/shared/{user_id}")
async def get_projects_shared_with_user(user_id: int):
    """
    Lister les projets partagés avec un utilisateur
    """
    result = project_service.get_projects_shared_with_user(user_id)
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Erreur lors de la récupération des projets partagés"))