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
Application Settings and Configuration
Centralized configuration management for the backend
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Application Info
    app_title: str = "Data quality Self-Service Backend"
    app_description: str = "Backend API for Data Quality and Management Tools"
    app_version: str = "1.0.0"
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # CORS Settings
    cors_origins: list = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: list = ["*"]
    cors_allow_headers: list = ["*"]
    
    # Databricks Configuration
    databricks_server_hostname: str = os.getenv('DATABRICKS_SERVER_HOSTNAME', '')
    databricks_http_path: str = os.getenv('DATABRICKS_HTTP_PATH', '')
    databricks_host: str = os.getenv('DATABRICKS_HOST', '')
    job_id: str = os.getenv('JOB_ID', '')
    
    # Azure Service Principal
    arm_client_id: str = os.getenv('ARM_CLIENT_ID', '')
    arm_client_secret: str = os.getenv('ARM_CLIENT_SECRET', '')
    arm_tenant_id: str = os.getenv('ARM_TENANT_ID', '')

    # Unity Catalog (for DQ results tables — NOT the app database)
    uc_catalog: str = os.getenv('UC_CATALOG', '')
    uc_schema: str = os.getenv('UC_SCHEMA', 'db_gdm_data_quality_app')
    uc_results_schema: str = os.getenv('UC_RESULTS_SCHEMA', 'db_gdm_dq_results')
    
    # Lakebase PostgreSQL Database
    # Password is NOT cached here — read live from PGPASSWORD env var at connection time
    # (Databricks Apps auto-refreshes PGPASSWORD every hour)
    pg_host: str = os.getenv('PG_HOST', '')
    pg_port: int = int(os.getenv('PG_PORT', '5432'))
    pg_database: str = os.getenv('PG_DATABASE', '')
    pg_user: str = os.getenv('PG_USER', '')
    pg_schema: str = os.getenv('PG_SCHEMA', 'dq_app')
    pg_sslmode: str = os.getenv('PG_SSLMODE', 'require')
    
    # Trino/Starburst Configuration
    trino_host: str = os.getenv('TRINO_HOST', 'trino.example.com')
    trino_port: int = int(os.getenv('TRINO_PORT', '443'))
    trino_user: str = os.getenv('TRINO_USER', 'user')
    trino_password: str = os.getenv('TRINO_PASSWORD', 'password')
    
    # UC Volume for CSV uploads (replaces DBFS)
    uc_upload_volume: str = os.getenv('UC_UPLOAD_VOLUME', '')
    
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create settings instance"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
