-- Data Quality App Schema
-- Lakebase PostgreSQL 

-- Create schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS dq_app;


-- Set search path
SET search_path TO dq_app;

-- ==================== Data Quality Tables ====================

-- Users table - tracks all users who access the application
CREATE TABLE IF NOT EXISTS users (
    id BIGINT NOT NULL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    username VARCHAR(255),
    first_login_at TIMESTAMP,
    last_login_at TIMESTAMP,
    login_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User sessions table - track user sessions
CREATE TABLE IF NOT EXISTS user_sessions (
    id BIGINT NOT NULL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    session_start TIMESTAMP,
    session_end TIMESTAMP,
    ip_address VARCHAR(45),
    user_agent TEXT
);

-- Activity log table - track user activities
CREATE TABLE IF NOT EXISTS activity_log (
    id BIGINT NOT NULL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    activity_type VARCHAR(50) NOT NULL,
    activity_description TEXT,
    page VARCHAR(100),
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- DQ Projects table - stores data quality project configurations
CREATE TABLE IF NOT EXISTS dq_projects (
    id BIGINT NOT NULL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    project_name VARCHAR(255) NOT NULL,
    description TEXT,
    source_type VARCHAR(50),
    config TEXT,
    status VARCHAR(50) DEFAULT 'draft',
    step INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- DQ Jobs table - stores Databricks job configurations
CREATE TABLE IF NOT EXISTS dq_jobs (
    id BIGINT NOT NULL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES dq_projects(id),
    job_name VARCHAR(255) NOT NULL,
    job_description TEXT,
    databricks_job_id BIGINT,
    databricks_job_url TEXT,
    workspace_path VARCHAR(500),
    notification_email VARCHAR(255),
    failure_action VARCHAR(50),
    retry_attempts INTEGER DEFAULT 0,
    priority VARCHAR(20) DEFAULT 'Medium',
    status VARCHAR(50) DEFAULT 'pending',
    deployed_by VARCHAR(255),
    schedule_cron VARCHAR(100),
    schedule_timezone VARCHAR(50) DEFAULT 'UTC',
    source_type VARCHAR(50),
    source_config TEXT,
    quality_config TEXT,
    is_primary BOOLEAN DEFAULT FALSE,
    run_count INTEGER DEFAULT 0,
    step INTEGER DEFAULT 1,
    deployment_config TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_run_at TIMESTAMP
);

-- DQ Tasks table - stores individual quality check tasks (each task = one check)
CREATE TABLE IF NOT EXISTS dq_tasks (
    id BIGINT NOT NULL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES dq_jobs(id),
    task_key VARCHAR(255) NOT NULL,
    task_name VARCHAR(255) NOT NULL,
    component_id VARCHAR(100) NOT NULL,
    component_name VARCHAR(255),
    category VARCHAR(100),
    notebook_path VARCHAR(500),
    check_config TEXT,
    thresholds TEXT,
    task_order INTEGER,
    databricks_task_key VARCHAR(255),
    is_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- DQ Executions table - tracks job execution runs
CREATE TABLE IF NOT EXISTS dq_executions (
    id BIGINT NOT NULL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES dq_jobs(id),
    databricks_run_id BIGINT,
    run_url TEXT,
    status VARCHAR(50),
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration_seconds INTEGER,
    triggered_by VARCHAR(255),
    trigger_type VARCHAR(50),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- DQ Task Results table - stores results for each check in an execution
CREATE TABLE IF NOT EXISTS dq_task_results (
    id BIGINT NOT NULL PRIMARY KEY,
    execution_id BIGINT NOT NULL REFERENCES dq_executions(id),
    task_id BIGINT NOT NULL REFERENCES dq_tasks(id),
    task_key VARCHAR(255) NOT NULL,
    status VARCHAR(50),
    rows_checked BIGINT,
    rows_passed BIGINT,
    rows_failed BIGINT,
    quality_score DOUBLE PRECISION,
    threshold_met BOOLEAN,
    error_message TEXT,
    result_details TEXT,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration_seconds INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- DQ Schedules table - manages scheduled job executions
CREATE TABLE IF NOT EXISTS dq_schedules (
    id BIGINT NOT NULL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES dq_jobs(id),
    schedule_type VARCHAR(50),
    cron_expression VARCHAR(100),
    timezone VARCHAR(50) DEFAULT 'UTC',
    is_active BOOLEAN DEFAULT TRUE,
    next_run_at TIMESTAMP,
    created_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- DQ Alerts table - stores quality check alerts and notifications
CREATE TABLE IF NOT EXISTS dq_alerts (
    id BIGINT NOT NULL PRIMARY KEY,
    execution_id BIGINT NOT NULL REFERENCES dq_executions(id),
    task_id BIGINT,
    alert_type VARCHAR(50),
    severity VARCHAR(20),
    message TEXT,
    notification_sent BOOLEAN DEFAULT FALSE,
    notification_email VARCHAR(255),
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_by VARCHAR(255),
    acknowledged_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- DQ Notebooks table - stores uploaded notebook metadata
CREATE TABLE IF NOT EXISTS dq_notebooks (
    id BIGINT NOT NULL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES dq_jobs(id),
    notebook_name VARCHAR(255) NOT NULL,
    notebook_path VARCHAR(500) NOT NULL,
    notebook_type VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- DQ Dashboards table - stores Databricks BI dashboard information
CREATE TABLE IF NOT EXISTS dq_dashboards (
    id BIGINT NOT NULL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES dq_jobs(id),
    execution_id BIGINT,
    dashboard_id VARCHAR(255) NOT NULL,
    dashboard_name VARCHAR(500),
    dashboard_url TEXT NOT NULL,
    catalog VARCHAR(100),
    results_schema VARCHAR(100),
    status VARCHAR(50),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==================== Indexes ====================
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_log_user_id ON activity_log(user_id);
CREATE INDEX IF NOT EXISTS idx_dq_projects_user_id ON dq_projects(user_id);
CREATE INDEX IF NOT EXISTS idx_dq_jobs_project_id ON dq_jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_dq_tasks_job_id ON dq_tasks(job_id);
CREATE INDEX IF NOT EXISTS idx_dq_executions_job_id ON dq_executions(job_id);
CREATE INDEX IF NOT EXISTS idx_dq_executions_run_id ON dq_executions(databricks_run_id);
CREATE INDEX IF NOT EXISTS idx_dq_task_results_execution_id ON dq_task_results(execution_id);
CREATE INDEX IF NOT EXISTS idx_dq_schedules_job_id ON dq_schedules(job_id);
CREATE INDEX IF NOT EXISTS idx_dq_dashboards_job_id ON dq_dashboards(job_id);
CREATE INDEX IF NOT EXISTS idx_dq_dashboards_execution_id ON dq_dashboards(execution_id);


UPDATE dq_app.dq_dashboards
SET dashboard_url = REPLACE(dashboard_url, '/dashboardsv3/', '/sql/dashboardsv3/')
WHERE dashboard_url LIKE '%/dashboardsv3/%'
  AND dashboard_url NOT LIKE '%/sql/dashboardsv3/%';



----------------- ADD Shared project table that references dq_project ----------------
------------ Ex: Project X is shared with user Y ------------------------------

CREATE TABLE IF NOT EXISTS dq_project_shares (
    project_id BIGINT NOT NULL REFERENCES dq_projects(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (project_id, user_id)
);

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE dq_project_shares TO "<DATABRICKS_CLIENT_ID>";


-- Add OpenMetadata FQN column
ALTER TABLE dq_app.dq_jobs ADD COLUMN IF NOT EXISTS omd_fqn VARCHAR(500);

----------- Create dq_omd_executions table ------------------

-- Tracks each OMD publish run triggered after a DQ job execution.


CREATE TABLE IF NOT EXISTS dq_app.dq_omd_executions (
    id                   SERIAL PRIMARY KEY,
    job_id               INTEGER NOT NULL REFERENCES dq_app.dq_jobs(id) ON DELETE CASCADE,
    databricks_job_id    TEXT,
    databricks_run_id    TEXT,
    run_url              TEXT,
    omd_fqn              TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'submitted',  -- submitted / completed / failed
    columns_pushed       INTEGER,
    error_message        TEXT,
    pushed_at            TIMESTAMP DEFAULT NOW(),
    completed_at         TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dq_omd_executions_job_id ON dq_app.dq_omd_executions(job_id);
CREATE INDEX IF NOT EXISTS idx_dq_omd_executions_status  ON dq_app.dq_omd_executions(status);

------------ correction of id ------

ALTER TABLE dq_app.dq_omd_executions ALTER COLUMN id TYPE BIGINT;
ALTER TABLE dq_app.dq_omd_executions ALTER COLUMN job_id TYPE BIGINT;


-- ==================== Provide Access to DB Lakebase to Databricks App (backend)  ====================

-- 1. Acvtivate Extension OAuth
CREATE EXTENSION IF NOT EXISTS databricks_auth;

-- 2. Create role postgres for service principal (backend app)
SELECT databricks_create_role('<DATABRICKS_CLIENT_ID>', 'service_principal');

-- 3. Authorize connection to the database
GRANT CONNECT ON DATABASE db_gdm_data_quality_app TO "<DATABRICKS_CLIENT_ID>";

-- 4. Authorize creation/reading in the dq_app schema
GRANT CREATE, USAGE ON SCHEMA dq_app TO "<DATABRICKS_CLIENT_ID>";

-- 5. ⚠️ MANDATORY - Access to existing tables
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA dq_app TO "<DATABRICKS_CLIENT_ID>";


-- grant access to new table dq_executions

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE dq_app.dq_omd_executions TO "<DATABRICKS_CLIENT_ID>";
GRANT USAGE, SELECT ON SEQUENCE dq_app.dq_omd_executions_id_seq 
TO "<DATABRICKS_CLIENT_ID>";






