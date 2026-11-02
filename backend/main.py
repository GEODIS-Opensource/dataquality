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
Data quality Self-Service Platform - Backend API
Modular FastAPI application with clean architecture
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import logging
import traceback
from contextlib import asynccontextmanager
from contextvars import ContextVar

# ContextVar for the current request's OAuth token.
# Unlike threading.local(), ContextVar is scoped per async task (per request),
# so concurrent requests never overwrite each other's token.
_request_token: ContextVar[str] = ContextVar('lakebase_request_token', default='')

def set_request_token(token: str):
    _request_token.set(token)

def get_request_token() -> str:
    return _request_token.get()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import configuration
from config.settings import get_settings

# Import API routers
from api import users, projects, jobs, datasources

# Initialize settings
settings = get_settings()

# Lifespan handler to diagnose services on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Log service initialization status on startup"""
    logger.info("=" * 80)
    logger.info("APPLICATION STARTUP - Checking Service Status")
    logger.info("=" * 80)

    # Check jobs service status
    from api.jobs import job_service
    if job_service is None:
        logger.error("JobService is None - initialization failed!")
    else:
        logger.info("JobService initialized")
        if hasattr(job_service, 'deployment_service'):
            dep_service = job_service.deployment_service
            if hasattr(dep_service, 'client'):
                if dep_service.client is None:
                    logger.error("DatabricksDeploymentService.client is None!")
                else:
                    logger.info(f"DatabricksDeploymentService.client initialized: {type(dep_service.client)}")
                    logger.info(f"Host: {dep_service.host}")
            else:
                logger.error("DatabricksDeploymentService has no 'client' attribute")
        else:
            logger.error("JobService has no 'deployment_service' attribute")

    logger.info("=" * 80)
    yield

# Create FastAPI app
app = FastAPI(
    title=settings.app_title,
    description=settings.app_description,
    version=settings.app_version,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

# Request logging middleware (errors only)
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Capture OBO token for Lakebase auth and log errors"""
    # Extract the user's OBO token and store it for the DB connection layer
    obo_token = request.headers.get('x-user-token', '') or request.headers.get('x-forwarded-access-token', '')
    if obo_token:
        set_request_token(obo_token)
    else:
        # Fallback: extract Bearer token from Authorization header
        auth = request.headers.get('authorization', '')
        if auth.startswith('Bearer '):
            set_request_token(auth[7:])
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        logger.error(f"[ERROR] Unhandled exception: {str(e)}")
        logger.error(traceback.format_exc())
        raise

# Include routers

# Telemetry endpoint for fluent-bit-status
@app.get("/.telemetry/fluent-bit-status")
async def fluent_bit_status():
    return {"status": "ok"}

app.include_router(users.router)
app.include_router(projects.router)
app.include_router(jobs.router)
app.include_router(datasources.router)

# ==================== Health & Info Endpoints ====================

@app.get("/")
def root():
    """Root endpoint - API information"""
    return {
        "message": "Data quality Self-Service API",
        "status": "healthy",
        "docs": "/docs",
        "api_version": settings.app_version
    }


@app.get("/api/")
async def health(request: Request):
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": settings.app_title,
        "timestamp": datetime.now().isoformat(),
        "database": "connected"
    }


# ==================== Placeholder Endpoints (Future Development) ====================

@app.post("/api/contracts/ddl/update")
async def update_ddl(table: str, ddl: str):
    """
    Update table DDL
    
    TODO: Implement OpenMetadata integration for contract management
    """
    return {
        "status": "success",
        "message": "TODO: Implement OpenMetadata integration"
    }


@app.get("/api/contracts/topics")
async def get_topics():
    """
    Get Kafka topics
    
    TODO: Implement Kafka integration for streaming contracts
    """
    return {
        "status": "success",
        "topics": [],
        "message": "TODO: Implement Kafka integration"
    }


@app.get("/api/monitoring/metrics")
async def get_metrics():
    """
    Get monitoring metrics
    
    TODO: Implement metrics collection and aggregation
    """
    return {
        "status": "success",
        "metrics": {},
        "message": "TODO: Implement metrics collection"
    }


# ==================== Application Entry Point ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port
    )

