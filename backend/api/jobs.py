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
Job API Endpoints
All job execution and monitoring routes
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from typing import Dict, Any
from models.schemas import DataQualityPayload
from services import JobService
import logging
import json

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dq", tags=["jobs"])

JOB_SERVICE_NOT_INITIALIZED = "Job service not initialized"
JOB_NOT_FOUND = "Job not found"

# Initialize service with error handling
try:
    job_service = JobService()
    logger.info("JobService initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize JobService: {str(e)}", exc_info=True)
    job_service = None


@router.post("/jobs/deploy")
async def deploy_dq_job_new(request: Request, deployment_data: Dict[str, Any]):
    """
    Deploy a complete data quality job to Databricks with real-time streaming updates
    
    Creates notebooks, uploads to workspace, and creates Databricks job with tasks
    Returns Server-Sent Events (SSE) stream for real-time progress updates
    """
    try:
        if job_service is None:
            raise HTTPException(status_code=500, detail=JOB_SERVICE_NOT_INITIALIZED)
        
        # Extract user's email from request body
        user_email = deployment_data.get('user_email')
        project_id = deployment_data.get('project_id')
        project_config = deployment_data.get('project_config', {})
        enabled_components = deployment_data.get('enabled_components', [])
        deployment_config = deployment_data.get('deployment_config', {})
        
        logger.info("Deploying job for project %s, user: %s",
                    str(project_id).replace('\n', '_').replace('\r', '_'),
                    str(user_email).replace('\n', '_').replace('\r', '_'))
        
        if not project_id:
            raise HTTPException(status_code=400, detail="project_id is required")
        
        if not enabled_components:
            raise HTTPException(status_code=400, detail="At least one component must be enabled")
        
        # Create SSE generator
        async def event_generator():
            """Generate Server-Sent Events for deployment progress"""
            try:
                # Deploy job using service generator (yields status updates)
                for update in job_service.deploy_dq_job(
                    project_id,
                    project_config,
                    enabled_components,
                    deployment_config,
                    user_email=user_email
                ):
                    # Ensure update is a dict
                    if not isinstance(update, dict):
                        logger.warning(f"Received non-dict update: {type(update)} - {update}")
                        update = {
                            'step': 'warning',
                            'status': 'warning',
                            'message': f'Received unexpected update format: {str(update)[:100]}'
                        }
                    
                    # Format as SSE event
                    event_data = json.dumps(update)
                    yield f"data: {event_data}\n\n"
                    
                    # If error, stop streaming
                    if update.get('status') == 'error':
                        break
                        
            except Exception as e:
                logger.error(f"Error in deployment stream: {str(e)}", exc_info=True)
                error_event = json.dumps({
                    'step': 'error',
                    'status': 'error',
                    'message': f'Deployment error: {str(e)}'
                })
                yield f"data: {error_event}\n\n"
        
        # Return SSE stream
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable buffering for nginx
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Deployment error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Deployment error: {str(e)}")


@router.post("/execute")
async def execute_dq_job(payload: DataQualityPayload):
    """
    Execute data quality job - creates Databricks job with tasks for each check
    
    TODO: Implement direct execution with Unity Catalog integration
    """
    raise HTTPException(
        status_code=501, 
        detail="TODO: Implement DQ execute endpoint with Unity Catalog"
    )


@router.post("/jobs/deploy_legacy")
async def deploy_dq_job(payload: DataQualityPayload):
    """Deploy data quality job to Databricks with tasks for each check (legacy)"""
    result = job_service.deploy_job(
        project_id=payload.metadata.get('project_id'),
        deployment_config=payload.deployment,
        quality_controls=payload.quality_controls.get('controls', [])
    )
    
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Deployment failed"))


@router.post("/jobs/{job_id}/run")
async def run_dq_job(job_id: int, request: Request, parameters: Dict[str, str] = None):
    """Execute a deployed data quality job"""
    user_email = request.headers.get('X-User-Email', 'system')
    
    result = job_service.run_job(job_id, triggered_by=user_email, parameters=parameters)
    
    if result.get("status") == "success":
        return result
    elif result.get("message") == JOB_NOT_FOUND:
        raise HTTPException(status_code=404, detail=JOB_NOT_FOUND)
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Execution failed"))


@router.get("/jobs/{job_id}")
async def get_job_details(job_id: int):
    """Get job details by ID (3-layer architecture)"""
    result = job_service.get_job_by_id(job_id)
    
    if result.get("status") == "success":
        return result
    elif result.get("message") == JOB_NOT_FOUND:
        raise HTTPException(status_code=404, detail=JOB_NOT_FOUND)
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to get job details"))


@router.get("/jobs/{job_id}/status")
async def get_job_status(job_id: int):
    """Get status of all executions for a job"""
    result = job_service.get_job_status(job_id)
    
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to get job status"))


@router.get("/executions/{execution_id}/results")
async def get_execution_results(execution_id: int):
    """Get detailed results for a specific execution"""
    result = job_service.get_execution_results(execution_id)
    
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to get execution results"))


@router.get("/jobs/{job_id}/runs/{run_id}/status")
async def get_run_status_live(job_id: int, run_id: str):
    """Get live status from Databricks for a specific run"""
    if job_service is None:
        raise HTTPException(status_code=500, detail=JOB_SERVICE_NOT_INITIALIZED)
    
    result = job_service.get_run_status_live(job_id, run_id)
    
    if result.get("status") == "success":
        return result
    elif result.get("message") == JOB_NOT_FOUND:
        raise HTTPException(status_code=404, detail=JOB_NOT_FOUND)
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to get run status"))


@router.get("/jobs/{job_id}/runs/{run_id}/output")
async def get_run_output(job_id: int, run_id: str):
    """Get output and results from a completed run"""
    if job_service is None:
        raise HTTPException(status_code=500, detail=JOB_SERVICE_NOT_INITIALIZED)
    
    result = job_service.get_run_output(job_id, run_id)
    
    if result.get("status") == "success":
        return result
    elif result.get("message") == JOB_NOT_FOUND:
        raise HTTPException(status_code=404, detail=JOB_NOT_FOUND)
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to get run output"))


@router.get("/jobs/{job_id}/executions")
async def get_execution_history(job_id: int, limit: int = 20):
    """Get execution history for a job"""
    if job_service is None:
        raise HTTPException(status_code=500, detail=JOB_SERVICE_NOT_INITIALIZED)
    
    result = job_service.get_execution_history(job_id, limit=limit)
    
    if result.get("status") == "success":
        return result
    elif result.get("message") == JOB_NOT_FOUND:
        raise HTTPException(status_code=404, detail=JOB_NOT_FOUND)
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to get execution history"))


@router.get("/executions/{execution_id}/dashboard")
async def get_execution_dashboard(execution_id: int):
    """Get dashboard information for a specific execution"""
    if job_service is None:
        raise HTTPException(status_code=500, detail=JOB_SERVICE_NOT_INITIALIZED)
    
    result = job_service.get_execution_dashboard(execution_id)
    
    if result.get("status") == "success":
        return result
    elif result.get("message") == "Dashboard not found":
        raise HTTPException(status_code=404, detail="Dashboard not found for this execution")
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to get dashboard info"))


@router.get("/jobs/{job_id}/dashboards")
async def get_job_dashboards(job_id: int):
    """Get all dashboards for a job"""
    if job_service is None:
        raise HTTPException(status_code=500, detail=JOB_SERVICE_NOT_INITIALIZED)
    
    result = job_service.get_job_dashboards(job_id)
    
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to get dashboards"))


@router.post("/jobs/{job_id}/schedule")
async def schedule_job(job_id: int, schedule_config: Dict[str, Any]):
    """Configure schedule for a Databricks job"""
    if job_service is None:
        raise HTTPException(status_code=500, detail=JOB_SERVICE_NOT_INITIALIZED)
    
    result = job_service.schedule_job(job_id, schedule_config)
    
    if result.get("status") == "success":
        return result
    elif result.get("message") == JOB_NOT_FOUND:
        raise HTTPException(status_code=404, detail=JOB_NOT_FOUND)
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to schedule job"))


@router.put("/jobs/{job_id}")
async def update_job(job_id: int, job_update_data: Dict[str, Any]):
    """
    Update job configuration (for 3-layer architecture auto-save)
    
    Supports updating: job_name, job_description, step, source_config, quality_config,
                      schedule_cron, schedule_timezone, deployed_by, status, etc.
    """
    if job_service is None:
        raise HTTPException(status_code=500, detail=JOB_SERVICE_NOT_INITIALIZED)
    
    result = job_service.update_job(job_id, job_update_data)
    
    if result.get("status") == "success":
        return result
    elif result.get("message") == JOB_NOT_FOUND:
        raise HTTPException(status_code=404, detail=JOB_NOT_FOUND)
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to update job"))


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: int):
    """
    Delete a job by ID
    """
    if job_service is None:
        raise HTTPException(status_code=500, detail=JOB_SERVICE_NOT_INITIALIZED)
    
    result = job_service.delete_job(job_id)
    
    if result.get("status") == "success":
        return result
    elif result.get("message") == JOB_NOT_FOUND:
        raise HTTPException(status_code=404, detail=JOB_NOT_FOUND)
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to delete job"))


@router.get("/jobs/{job_id}/report")
async def get_job_report(job_id: int):
    """
    Get job execution report from summary table
    
    Fetches data from dbr_prd01_gdm.db_gdm_dq_results.dq_{project}_{job}_summary_dataset
    """
    if job_service is None:
        raise HTTPException(status_code=500, detail=JOB_SERVICE_NOT_INITIALIZED)
    
    result = job_service.get_job_report(job_id)
    
    if result.get("status") == "success":
        return result
    elif result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=result.get("message", "Report not found"))
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to get report"))


@router.get("/jobs/{job_id}/faulty-records/download")
async def download_faulty_records(job_id: int):
    """Download faulty records as CSV for a given job"""
    from fastapi.responses import StreamingResponse
    if job_service is None:
        raise HTTPException(status_code=500, detail=JOB_SERVICE_NOT_INITIALIZED)

    result = job_service.download_faulty_records(job_id)

    if result.get("status") == "success":
        csv_content = result.get("csv_content", "")
        filename    = result.get("filename", "faulty_records.csv")
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    elif result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=result.get("message", "Faulty records table not found"))
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to download faulty records"))


@router.post("/jobs/{job_id}/publish-to-openmetadata")
async def publish_to_openmetadata(request: Request, job_id: int, body: Dict[str, Any]):
    """
    Publish the latest DQ run results to OpenMetadata.
    Persists the FQN in dq_jobs.omd_fqn for future pre-fill.

    Body: { "omd_fqn": "service.schema.table" }
    """
    if job_service is None:
        raise HTTPException(status_code=500, detail=JOB_SERVICE_NOT_INITIALIZED)

    omd_fqn = (body.get("omd_fqn") or "").strip()
    if not omd_fqn:
        raise HTTPException(status_code=400, detail="omd_fqn is required")

    result = job_service.publish_to_openmetadata(job_id, omd_fqn)

    if result.get("status") in ("success", "submitted"):
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to publish to OpenMetadata"))


@router.patch("/jobs/{job_id}/omd-executions/{exec_id}/status")
async def update_omd_execution_status(request: Request, job_id: int, exec_id: int, body: Dict[str, Any]):
    """
    Update the status of an OMD execution record.
    Called by the frontend polling fragment when the Databricks run completes or fails.

    Body: {
        "status": "completed" | "failed",
        "columns_pushed": 5,          // optional, on success
        "error_message": "..."        // optional, on failure
    }
    """
    status = (body.get("status") or "").strip()
    if status not in ("completed", "failed"):
        raise HTTPException(status_code=400, detail="status must be 'completed' or 'failed'")

    from database.repositories.job_repository import JobRepository
    ok = JobRepository.update_omd_execution_status(
        exec_id=exec_id,
        status=status,
        columns_pushed=body.get("columns_pushed"),
        error_message=body.get("error_message"),
    )
    if ok:
        return {"status": "success", "exec_id": exec_id}
    raise HTTPException(status_code=500, detail="Failed to update OMD execution status")


@router.get("/jobs/{job_id}/omd-executions")
async def get_omd_executions(request: Request, job_id: int):
    """Return the OMD publish history for a given DQ job."""
    from database.repositories.job_repository import JobRepository
    executions = JobRepository.get_omd_executions_by_job(job_id)
    return {"status": "success", "executions": executions}


@router.patch("/jobs/{job_id}/omd-fqn")
async def update_job_omd_fqn(request: Request, job_id: int, body: Dict[str, Any]):
    """Persist or clear the OpenMetadata FQN on a job row.

    Body: { "omd_fqn": "service.schema.table" }
    Passing an empty string will clear the column in the DB.
    """
    if job_service is None:
        raise HTTPException(status_code=500, detail=JOB_SERVICE_NOT_INITIALIZED)

    omd_fqn = (body.get("omd_fqn") or "").strip()

    from database.repositories.job_repository import JobRepository
    ok = JobRepository.update_omd_fqn(job_id, omd_fqn)
    if ok:
        return {"status": "success", "omd_fqn": omd_fqn}
    raise HTTPException(status_code=500, detail="Failed to update omd_fqn")


@router.get("/jobs/{job_id}/omd-executions/latest-status")
async def get_omd_latest_status(request: Request, job_id: int):
    """Return the latest OMD push `status` for a given DQ job (single string)."""
    from database.repositories.job_repository import JobRepository
    status_val = JobRepository.get_latest_omd_status_by_job(job_id)
    if status_val is None:
        return {"status": "not_found", "omd_status": None}
    return {"status": "success", "omd_status": status_val}

