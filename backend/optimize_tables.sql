-- ========================================
-- Optimization Script for Data Quality Tables
-- Run these commands periodically to maintain query performance
-- ========================================

-- IMPORTANT: For Delta Lake tables, choose ONE of these optimization strategies:
-- 1. Z-ORDER (manual optimization) - for tables with known query patterns
-- 2. Liquid Clustering (automatic optimization) - newer feature, auto-optimizes

-- Use the schema
USE SCHEMA db_gdm_data_quality_app;

-- ========================================
-- OPTION 1: Z-ORDER Optimization (Recommended for existing Iceberg/Delta tables)
-- ========================================

-- Optimize users table and Z-ORDER by email (most common query pattern)
OPTIMIZE users ZORDER BY (email);

-- Optimize dq_projects table and Z-ORDER by user_id (foreign key queries)
OPTIMIZE dq_projects ZORDER BY (user_id);

-- Optimize dq_jobs table
OPTIMIZE dq_jobs ZORDER BY (project_id);

-- Optimize dq_tasks table
OPTIMIZE dq_tasks ZORDER BY (job_id);

-- Optimize dq_executions table
OPTIMIZE dq_executions ZORDER BY (job_id);

-- Optimize dq_task_results table
OPTIMIZE dq_task_results ZORDER BY (execution_id);

-- ========================================
-- OPTION 2: Liquid Clustering (For new Delta tables only)
-- ========================================
-- Note: Requires recreating tables with CLUSTER BY clause
-- See schema_delta_clustered.sql for table definitions

-- ALTER TABLE users CLUSTER BY (email);
-- ALTER TABLE dq_projects CLUSTER BY (user_id);
-- ALTER TABLE dq_jobs CLUSTER BY (project_id);
-- ALTER TABLE dq_tasks CLUSTER BY (job_id);
-- ALTER TABLE dq_executions CLUSTER BY (job_id);
-- ALTER TABLE dq_task_results CLUSTER BY (execution_id);

-- Vacuum old snapshots (optional - removes old data versions)
-- Be careful with this - set retention period appropriately
-- VACUUM users RETAIN 168 HOURS;
-- VACUUM dq_projects RETAIN 168 HOURS;
-- VACUUM dq_jobs RETAIN 168 HOURS;

-- View table statistics
DESCRIBE EXTENDED users;
DESCRIBE EXTENDED dq_projects;

-- Check table file count (high file count = slow queries)
DESCRIBE DETAIL users;
DESCRIBE DETAIL dq_projects;
