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
User Repository - Database operations for users
Handles all user-related database queries
"""
import json
import uuid
import time
from typing import Optional, Dict, Any
from database.connection import get_db_connection, DB_CONFIG


def _generate_id() -> int:
    """Generate a unique ID using timestamp and UUID"""
    return int(time.time() * 1000000) + (uuid.uuid4().int % 1000000)


def _full_table(table_name: str) -> str:
    """Return schema-qualified table name for PostgreSQL"""
    return f"{DB_CONFIG['schema']}.{table_name}"


class UserRepository:
    """Repository for user database operations"""

    @staticmethod
    def list_users() -> list:
        """
        Return all users (id, email, username)
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            full_table = _full_table('users')
            cursor.execute(f"SELECT id, email, username FROM {full_table} WHERE is_active = true")
            rows = cursor.fetchall()
            cursor.close()
            return [
                {"id": row[0], "email": row[1], "username": row[2]} for row in rows
            ]

    @staticmethod
    def create_or_update_user(email: str, username: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Create a new user or update last login for existing user
        
        Args:
            email: User email address
            username: Optional username
            
        Returns:
            User record as dictionary or None
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            full_table = _full_table('users')
            
            # Escape single quotes
            email_escaped = email.replace("'", "''")
            username_escaped = username.replace("'", "''") if username else None
            
            # Check if user exists
            cursor.execute(f"SELECT * FROM {full_table} WHERE email = '{email_escaped}'")
            result = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            
            if result:
                # Update existing user
                username_clause = f"'{username_escaped}'" if username_escaped else "username"
                update_query = f"""
                    UPDATE {full_table}
                    SET last_login_at = CURRENT_TIMESTAMP,
                        username = COALESCE({username_clause}, username),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE email = '{email_escaped}'
                """
                cursor.execute(update_query)
                
                # Get updated user
                cursor.execute(f"SELECT * FROM {full_table} WHERE email = '{email_escaped}'")
                result = cursor.fetchall()
            else:
                # Create new user
                new_id = _generate_id()
                username_val = f"'{username_escaped}'" if username_escaped else "NULL"
                
                insert_query = f"""
                    INSERT INTO {full_table} (id, email, username, first_login_at, last_login_at, login_count, is_active, created_at, updated_at)
                    VALUES ({new_id}, '{email_escaped}', {username_val}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
                cursor.execute(insert_query)
                
                # Get created user
                cursor.execute(f"SELECT * FROM {full_table} WHERE email = '{email_escaped}'")
                result = cursor.fetchall()
            
            cursor.close()
            
            # Convert result to dict
            if result and len(result) > 0:
                row = result[0]
                return dict(zip(columns, row)) if columns else None
            return None
    
    @staticmethod
    def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
        """
        Get user by email address
        
        Args:
            email: User email address
            
        Returns:
            User record as dictionary or None
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            full_table = _full_table('users')
            
            email_escaped = email.replace("'", "''")
            cursor.execute(f"SELECT * FROM {full_table} WHERE email = '{email_escaped}'")
            result = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            cursor.close()
            
            if result and len(result) > 0:
                row = result[0]
                return dict(zip(columns, row)) if columns else None
            return None
    
    @staticmethod
    def create_session(email: str, user_agent: Optional[str] = None, ip_address: Optional[str] = None) -> Optional[int]:
        """
        Create a new user session
        
        Args:
            email: User email address
            user_agent: Browser user agent string
            ip_address: Client IP address
            
        Returns:
            Session ID or None
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                full_users_table = _full_table('users')
                full_sessions_table = _full_table('user_sessions')
                
                # Get user_id
                email_escaped = email.replace("'", "''")
                cursor.execute(f"SELECT id FROM {full_users_table} WHERE email = '{email_escaped}'")
                result = cursor.fetchall()
                
                if result and len(result) > 0:
                    user_id = result[0][0]
                    session_id = _generate_id()
                    
                    user_agent_val = f"'{user_agent.replace(chr(39), chr(39)+chr(39))}'" if user_agent else 'NULL'
                    ip_address_val = f"'{ip_address}'" if ip_address else 'NULL'
                    
                    insert_query = f"""
                        INSERT INTO {full_sessions_table} (id, user_id, session_start, session_end, ip_address, user_agent)
                        VALUES ({session_id}, {user_id}, CURRENT_TIMESTAMP, NULL, {ip_address_val}, {user_agent_val})
                    """
                    cursor.execute(insert_query)
                    cursor.close()
                    return session_id
                
                cursor.close()
                return None
        except Exception as e:
            print(f"Error creating session: {str(e)}")
            return None
    
    @staticmethod
    def update_login_count(email: str) -> bool:
        """
        Update login count based on number of sessions
        
        Args:
            email: User email address
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                full_users_table = _full_table('users')
                full_sessions_table = _full_table('user_sessions')
                
                email_escaped = email.replace("'", "''")
                
                # Count total sessions for user
                query = f"""
                    UPDATE {full_users_table}
                    SET login_count = (
                        SELECT COUNT(*) 
                        FROM {full_sessions_table} s
                        WHERE s.user_id = {full_users_table}.id
                    ),
                    updated_at = CURRENT_TIMESTAMP
                    WHERE email = '{email_escaped}'
                """
                cursor.execute(query)
                cursor.close()
                return True
        except Exception as e:
            print(f"Error updating login count: {str(e)}")
            return False
    
    @staticmethod
    def log_activity(user_email: str, activity_type: str, activity_description: Optional[str] = None, 
                    page: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Log user activity
        
        Args:
            user_email: User email address
            activity_type: Type of activity
            activity_description: Description of activity
            page: Page where activity occurred
            metadata: Additional metadata
            
        Returns:
            True if successful, False otherwise
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            full_users_table = _full_table('users')
            full_activity_table = _full_table('activity_log')
            
            # Escape single quotes
            user_email_escaped = user_email.replace("'", "''")
            activity_type_escaped = activity_type.replace("'", "''")
            activity_description_escaped = activity_description.replace("'", "''") if activity_description else None
            page_escaped = page.replace("'", "''") if page else None
            
            # Get user_id from email
            cursor.execute(f"SELECT id FROM {full_users_table} WHERE email = '{user_email_escaped}'")
            result = cursor.fetchall()
            
            if result and len(result) > 0:
                user_id = result[0][0]
                
                # Generate new ID for activity log
                activity_id = _generate_id()
                
                # Convert metadata to JSON string if provided
                metadata_str = json.dumps(metadata).replace("'", "''") if metadata else None
                metadata_val = f"'{metadata_str}'" if metadata_str else 'NULL'
                activity_desc_val = f"'{activity_description_escaped}'" if activity_description_escaped else 'NULL'
                page_val = f"'{page_escaped}'" if page_escaped else 'NULL'
                
                insert_query = f"""
                    INSERT INTO {full_activity_table} (id, user_id, activity_type, activity_description, page, metadata, created_at)
                    VALUES ({activity_id}, {user_id}, '{activity_type_escaped}', {activity_desc_val}, {page_val}, {metadata_val}, CURRENT_TIMESTAMP)
                """
                cursor.execute(insert_query)
                cursor.close()
                return True
            
            cursor.close()
            return False
