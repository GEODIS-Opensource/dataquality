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
Check dashboard setup - verify table exists and show execution statuses
"""
import sys
from database.db_utils import get_db_connection
from config.settings import Settings


def _print_executions(executions):
    """Print the recent executions table"""
    if not executions:
        print("❌ No executions found")
        return

    print(f"\nFound {len(executions)} recent executions:")
    print("\n{:<5} {:<15} {:<12} {:<20} {:<30}".format(
        "ID", "Run ID", "Status", "End Time", "Job Name"
    ))
    print("-" * 100)
    for execution in executions:
        exec_id, run_id, status, _start_time, end_time, raw_job_name = execution[:6]
        job_name = raw_job_name[:30] if raw_job_name else "N/A"
        status_symbol = "✅" if status in ['completed', 'success', 'SUCCESS'] else "❌"
        print(f"{status_symbol} {exec_id:<5} {str(run_id):<15} {status:<12} {str(end_time):<20} {job_name:<30}")


def _print_dashboards(dashboards):
    """Print the existing dashboards"""
    if not dashboards:
        print("ℹ️  No dashboards created yet")
        return

    print(f"\nFound {len(dashboards)} dashboards:")
    for dash in dashboards:
        print(f"  - ID: {dash[0]}, Job: {dash[1]}, Execution: {dash[2]}, Status: {dash[4]}")
        print(f"    Name: {dash[3]}")

def check_dashboard_table():
    """Check if dq_dashboards table exists"""
    print("\n" + "="*80)
    print("CHECKING DASHBOARD TABLE")
    print("="*80 + "\n")
    
    try:
        settings = Settings()
        catalog = settings.DATABRICKS_CATALOG
        schema = settings.DATABRICKS_SCHEMA
        
        print(f"Using catalog: {catalog}")
        print(f"Using schema: {schema}")
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Check if table exists
            print("\n1. Checking if dq_dashboards table exists...")
            query = f"""
                SHOW TABLES IN {catalog}.{schema} LIKE 'dq_dashboards'
            """
            cursor.execute(query)
            tables = cursor.fetchall()
            
            if tables:
                print("✅ dq_dashboards table EXISTS")
                print(f"   Result: {tables}")
            else:
                print("❌ dq_dashboards table DOES NOT EXIST")
                print("\n⚠️  You need to run this SQL in Databricks:")
                print(f"""
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.dq_dashboards (
    id BIGINT NOT NULL,
    job_id BIGINT NOT NULL,
    execution_id BIGINT,
    dashboard_id VARCHAR(255) NOT NULL,
    dashboard_name VARCHAR(500),
    dashboard_url STRING NOT NULL,
    catalog VARCHAR(100),
    results_schema VARCHAR(100),
    status VARCHAR(50),
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    error_message STRING
) USING DELTA;
""")
                return False
            
            # Check recent executions and their statuses
            print("\n2. Checking recent execution statuses...")
            query = f"""
                SELECT 
                    e.id,
                    e.databricks_run_id,
                    e.status,
                    e.start_time,
                    e.end_time,
                    j.job_name
                FROM {catalog}.{schema}.dq_executions e
                JOIN {catalog}.{schema}.dq_jobs j ON e.job_id = j.id
                ORDER BY e.id DESC
                LIMIT 10
            """
            cursor.execute(query)
            executions = cursor.fetchall()
            _print_executions(executions)
            
            # Check if any dashboards exist
            print("\n3. Checking existing dashboards...")
            query = f"""
                SELECT 
                    id,
                    job_id,
                    execution_id,
                    dashboard_name,
                    status,
                    created_at
                FROM {catalog}.{schema}.dq_dashboards
                ORDER BY id DESC
                LIMIT 5
            """
            cursor.execute(query)
            dashboards = cursor.fetchall()
            _print_dashboards(dashboards)
            
            return True
            
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n🔍 Dashboard Setup Checker")
    success = check_dashboard_table()
    sys.exit(0 if success else 1)
