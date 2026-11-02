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
Pydantic Models for Request/Response Validation
All API data models in one place
"""
from pydantic import BaseModel
from typing import Optional, Dict, Any


# ==================== User Models ====================

class UserLogin(BaseModel):
    """User login request"""
    email: str
    username: Optional[str] = None


class ActivityLog(BaseModel):
    """User activity logging request"""
    user_email: str
    activity_type: str
    activity_description: Optional[str] = None
    page: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# ==================== Project Models ====================

class ProjectCreate(BaseModel):
    """Create new project request"""
    name: str
    description: Optional[str] = ""


class ProjectUpdate(BaseModel):
    """Update project request"""
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    step: Optional[int] = None
    status: Optional[str] = None


# ==================== Data Quality Models ====================

class DataQualityPayload(BaseModel):
    """Complete DQ job payload"""
    metadata: Dict[str, Any]
    data_source: Dict[str, Any]
    quality_controls: Dict[str, Any]
    deployment: Dict[str, Any]
    execution: Dict[str, Any]


# ==================== Data Source Models ====================

class TableSchema(BaseModel):
    """Table schema identifier"""
    catalog: str
    schema: str
    table: str
