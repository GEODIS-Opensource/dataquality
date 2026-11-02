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
Datasource API Endpoints
All data source related routes (Starburst, CSV, etc.)
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Request
from typing import Annotated, Dict, Any, Optional
from models.schemas import TableSchema
from services import DatasourceService
import logging

router = APIRouter(prefix="/api/datasources", tags=["datasources"])
datasource_service = DatasourceService()


# ==================== Starburst/Trino Endpoints ====================

@router.get("/starburst/catalogs")
async def get_catalogs():
    """Get available Starburst catalogs"""
    result = datasource_service.get_catalogs()
    
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to fetch catalogs"))


@router.get("/starburst/schemas")
async def get_schemas(catalog: str):
    """Get schemas in a catalog"""
    result = datasource_service.get_schemas(catalog)
    
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to fetch schemas"))


@router.get("/starburst/tables")
async def get_tables(catalog: str, schema: str):
    """Get tables in a schema"""
    result = datasource_service.get_tables(catalog, schema)
    
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to fetch tables"))


@router.post("/starburst/preview")
async def preview_table(table_info: TableSchema):
    """Preview table data"""
    result = datasource_service.preview_table(
        table_info.catalog,
        table_info.schema,
        table_info.table
    )
    
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to preview table"))


# ==================== CSV Upload Endpoint ====================

@router.post("/csv/upload")
async def upload_csv(project_id: int, file: Annotated[UploadFile, File()], user_email: str = '', config: str = '{}'):
    """Upload CSV file to DBFS and update project config"""
    try:
        content = await file.read()
        result = datasource_service.upload_csv(project_id, file.filename, content, config, user_email)
        if result.get("status") == "success":
            return result
        else:
            raise HTTPException(status_code=500, detail=result.get("message", "Upload failed"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.post("/csv/save-to-project")
async def save_csv_to_project(save_data: Dict[str, Any]):
    """Save CSV file metadata to project config (stores only active file)"""
    result = datasource_service.save_csv_to_project_config(
        project_id=save_data.get('project_id'),
        file_metadata=save_data.get('file_metadata'),
        separator=save_data.get('separator'),
        quote_char=save_data.get('quote_char'),
        has_header=save_data.get('has_header'),
        skip_lines=save_data.get('skip_lines'),
        dataset_name=save_data.get('dataset_name')
    )
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Save failed"))

@router.get("/csv/list")
async def list_csv_files(project_id: int, user_email: str = ''):
    """List all CSV, TXT, JSON files uploaded for a project in DBFS"""
    result = datasource_service.list_csv_files(project_id, user_email)
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "List failed"))

@router.get("/csv/preview")
async def preview_csv(project_id: int, file_path: str):
    """Preview CSV file from DBFS, with config and stats"""
    result = datasource_service.preview_csv(project_id, file_path)
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Preview failed"))

@router.delete("/csv/delete")
async def delete_csv(project_id: int, file_path: str, user_email: str):
    """Delete CSV file from DBFS (only project owner can delete)"""
    result = datasource_service.delete_csv_file(project_id, file_path, user_email)
    if result.get("status") == "success":
        return result
    elif result.get("status") == "forbidden":
        raise HTTPException(status_code=403, detail=result.get("message", "Access denied"))
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Deletion failed"))


# ==================== Unity Catalog Endpoints ====================

def _extract_user_token(request: Request) -> Optional[str]:
    """Extract user authentication token from forwarded headers or Authorization header."""
    forwarded_token = request.headers.get("x-user-token", "") or request.headers.get("x-forwarded-access-token", "")
    if forwarded_token:
        logging.info(f"[Auth] Using forwarded user token (length: {len(forwarded_token)})")
        return forwarded_token

    auth_header = request.headers.get("Authorization", "")
    logging.info(f"[Auth] Authorization header present: {bool(auth_header)}, starts with Bearer: {auth_header.startswith('Bearer ')}")
    if auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
        logging.info(f"[Auth] Extracted user token (length: {len(token)})")
        return token
    logging.warning("[Auth] No forwarded user token or valid Authorization header found - using default authentication")
    return None

def _require_obo_token(request: Request) -> str:
    """Require a user token for OBO-only Unity Catalog access."""
    user_token = _extract_user_token(request)
    if not user_token:
        logging.warning("[OBO] Unity Catalog endpoint rejected: missing user token (OBO required)")
        raise HTTPException(
            status_code=401,
            detail="Unity Catalog access requires user OBO authentication. Please sign in again."
        )
    return user_token

@router.get("/unity-catalog/catalogs")
async def get_unity_catalogs(request: Request):
    """Get available Unity Catalog catalogs with user-level access filtering"""
    user_token = _require_obo_token(request)
    
    if user_token:
        logging.info(f"[OBO] Using on-behalf-of user authentication (token length: {len(user_token)})")
        
        # DEBUG: Decode JWT to see scopes
        try:
            import base64
            import json
            parts = user_token.split('.')
            if len(parts) >= 2:
                # Decode payload (add padding if needed)
                payload = parts[1]
                payload += '=' * (4 - len(payload) % 4)
                decoded = base64.b64decode(payload)
                token_data = json.loads(decoded)
                scopes = token_data.get('scope', 'NO SCOPE FIELD')
                logging.info(f"[OBO DEBUG] Token scopes: {scopes}")
        except Exception as e:
            logging.warning(f"[OBO DEBUG] Could not decode token: {e}")
    result = datasource_service.get_unity_catalogs(user_token=user_token)
    
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to fetch Unity Catalog catalogs"))


@router.get("/unity-catalog/schemas")
async def get_unity_schemas(request: Request, catalog: str):
    """Get schemas in a Unity Catalog catalog with user-level access filtering"""
    user_token = _require_obo_token(request)
    
    result = datasource_service.get_unity_schemas(catalog, user_token=user_token)
    
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to fetch schemas"))


@router.get("/unity-catalog/tables")
async def get_unity_tables(request: Request, catalog: str, schema: str):
    """Get tables in a Unity Catalog schema with user-level access filtering"""
    user_token = _require_obo_token(request)
    
    result = datasource_service.get_unity_tables(catalog, schema, user_token=user_token)
    
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to fetch tables"))


@router.post("/unity-catalog/preview")
async def preview_unity_table(request: Request, table_info: TableSchema):
    """Preview Unity Catalog table data with OBO authentication"""
    user_token = _require_obo_token(request)
    
    result = datasource_service.preview_unity_table(
        table_info.catalog,
        table_info.schema,
        table_info.table,
        user_token=user_token
    )
    
    # Return result as-is (both success and error cases)
    # Frontend will handle based on status field
    return result
