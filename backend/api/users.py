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
User API Endpoints
All user-related routes
"""

import logging
from fastapi import APIRouter, HTTPException
from models.schemas import UserLogin, ActivityLog
from services import UserService


router = APIRouter(prefix="/api/users", tags=["users"])
user_service = UserService()


@router.post("/login")
async def register_user_login(user_login: UserLogin):
    """Register or update user login"""
    result = user_service.register_login(user_login.email, user_login.username)
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Login failed"))


@router.get("/{email}")
async def get_user(email: str):
    """Get user information by email"""
    result = user_service.get_user(email)
    
    if result.get("status") == "success":
        return result
    elif result.get("message") == "User not found":
        raise HTTPException(status_code=404, detail="User not found")
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to get user"))


@router.post("/activity")
async def log_user_activity(activity: ActivityLog):
    """Log user activity"""
    result = user_service.log_activity(
        activity.user_email,
        activity.activity_type,
        activity.activity_description,
        activity.page,
        activity.metadata
    )
    
    # Always return success for activity logging (silent fail)
    return result

@router.get("")
async def list_users():
    """Return all users (id, email, username)"""
    users = user_service.list_users()
    return {"users": users}