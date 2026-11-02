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
User Service - Business logic for user operations
"""
from typing import Dict, Any, Optional
from database.repositories import UserRepository


import logging

class UserService:
    """Service for user-related business logic"""

    def list_users(self) -> list:
        """
        Return all users (id, email, username)
        """
        return self.repository.list_users()

    def __init__(self):
        self.repository = UserRepository()
    
    def register_login(self, email: str, username: Optional[str] = None) -> Dict[str, Any]:
        """
        Register or update user login
        
        Args:
            email: User email address
            username: Optional username
            
        Returns:
            Dictionary with status and user information
        """
        try:
            # Create or update user
            user = self.repository.create_or_update_user(email, username)
            if not user:
                logging.error("Failed to create or update user")
                return {
                    "status": "error",
                    "message": "Failed to create or update user"
                }
            # Create session
            session_id = self.repository.create_session(email)
            # Log activity
            self.repository.log_activity(email, "session_start", "New session started", "home")
            # Update login count
            self.repository.update_login_count(email)
            return {
                "status": "success",
                "user": user,
                "session_id": session_id,
                "message": "User login registered successfully"
            }
        except Exception as e:
            logging.error(f"User login failed: {str(e)}")
            return {
                "status": "error",
                "message": f"User login failed: {str(e)}"
            }
    
    def get_user(self, email: str) -> Dict[str, Any]:
        """
        Get user information by email
        
        Args:
            email: User email address
            
        Returns:
            Dictionary with status and user information
        """
        try:
            user = self.repository.get_user_by_email(email)
            
            if user:
                return {
                    "status": "success",
                    "user": user
                }
            else:
                return {
                    "status": "error",
                    "message": "User not found"
                }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to get user: {str(e)}"
            }
    
    def log_activity(self, user_email: str, activity_type: str, 
                    description: Optional[str] = None, page: Optional[str] = None,
                    metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Log user activity
        
        Args:
            user_email: User email address
            activity_type: Type of activity
            description: Activity description
            page: Page where activity occurred
            metadata: Additional metadata
            
        Returns:
            Dictionary with status
        """
        try:
            success = self.repository.log_activity(
                user_email, activity_type, description, page, metadata
            )
            
            if success:
                return {
                    "status": "success",
                    "message": "Activity logged successfully"
                }
            else:
                return {
                    "status": "warning",
                    "message": "User not found - activity not logged"
                }
        except Exception as e:
            # Silent fail for activity logging
            return {
                "status": "error",
                "message": str(e)
            }
