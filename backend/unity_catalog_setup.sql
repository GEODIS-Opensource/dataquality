# Create — GDM Data Quality App


# Unity Catalog Setup

> SQL commands to run on Databricks to provision the required permissions.

## 1. Create Schema & Volumes

CREATE SCHEMA IF NOT EXISTS <uc_catalog>.<uc_schema>
CREATE VOLUME IF NOT EXISTS <uc_catalog>.<uc_schema>.dq_uploads
CREATE SCHEMA IF NOT EXISTS <uc_catalog>.db_gdm_dq_results


## 2. Schema-level access — `<uc_catalog>.<uc_schema>`
```sql
-- Service principal: <DATABRICKS_SERVICE_PRINCIPAL>
GRANT USE SCHEMA
  ON SCHEMA <uc_catalog>.<uc_schema>
  TO `<DATABRICKS_SERVICE_PRINCIPAL>`;

-- App service principal: <DATABRICKS_BACKEND_SERVICE_PRINCIPAL>
GRANT USE SCHEMA
  ON SCHEMA <uc_catalog>.<uc_schema>
  TO `<DATABRICKS_BACKEND_SERVICE_PRINCIPAL>`;

-- App service principal: <DATABRICKS_BACKEND_SERVICE_PRINCIPAL>
GRANT USE SCHEMA
  ON SCHEMA <uc_catalog>.<uc_schema>
  TO `<DATABRICKS_BACKEND_SERVICE_PRINCIPAL>`;
```

## 2. Volume access — `<uc_catalog>.<uc_schema>.dq_uploads`

```sql
GRANT READ VOLUME
  ON VOLUME <uc_catalog>.<uc_schema>.dq_uploads
  TO `<DATABRICKS_SERVICE_PRINCIPAL>`;

GRANT WRITE VOLUME
  ON VOLUME <uc_catalog>.<uc_schema>.dq_uploads
  TO `<DATABRICKS_SERVICE_PRINCIPAL>`;
```

## 3. Schema-level access — `<uc_catalog>.db_gdm_dq_results`

```sql
GRANT USE SCHEMA
  ON SCHEMA <uc_catalog>.db_gdm_dq_results
  TO `<DATABRICKS_SERVICE_PRINCIPAL>`;

GRANT CREATE TABLE
  ON SCHEMA <uc_catalog>.db_gdm_dq_results
  TO `<DATABRICKS_SERVICE_PRINCIPAL>`;

GRANT MODIFY
  ON SCHEMA <uc_catalog>.db_gdm_dq_results
  TO `<DATABRICKS_SERVICE_PRINCIPAL>`;

GRANT SELECT
  ON SCHEMA <uc_catalog>.db_gdm_dq_results
  TO `<DATABRICKS_SERVICE_PRINCIPAL>`;
```

