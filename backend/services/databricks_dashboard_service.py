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
Databricks Dashboard Service
Automatically creates Databricks SQL/BI dashboards for DQ job results
"""
import os
import json
import logging
import requests
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

_COLUMN_NAME_EXPR = "`column_name`"
_COLUMN_NAME_DISPLAY = "Column Name"


class DatabricksDashboardService:
    """Service to create and manage Databricks BI dashboards for DQ results"""
    
    def __init__(self):
        """Initialize Databricks API client"""
        self.host = ''
        self.token = ''
        self._init_credentials()
    
    def _init_credentials(self):
        """Initialize API credentials via Azure Service Principal"""
        try:
            from config.databricks_auth import get_access_token, get_host
            
            self.host = get_host()
            self.token = get_access_token()
            
            if not self.host or not self.token:
                raise RuntimeError(
                    f"Missing required credentials: host={'SET' if self.host else 'MISSING'}, token={'SET' if self.token else 'MISSING'}"
                )
            
            logger.info(f"[DASHBOARD] ✅ Credentials initialized for host: {self.host}")
            
        except Exception as e:
            logger.error(f"[DASHBOARD] ❌ Initialization failed: {e}")
            raise RuntimeError(f"Failed to initialize Databricks credentials: {e}") from e
    
    def _make_api_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Make a request to Databricks REST API"""
        url = f"https://{self.host}{endpoint}"
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
        
        logger.info(f"[API_REQUEST] {method} {endpoint}")
        if data:
            logger.info(f"[API_REQUEST] Request data: {json.dumps(data, indent=2)}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=data)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json=data)
            elif method == 'PATCH':
                response = requests.patch(url, headers=headers, json=data)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            result = response.json() if response.text else {}
            logger.info(f"[API_REQUEST] ✅ Success - Status: {response.status_code}")
            logger.info(f"[API_REQUEST] Response: {json.dumps(result, indent=2)[:500]}...")
            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"[API_REQUEST] ❌ Request failed: {method} {url}")
            logger.error(f"[API_REQUEST] Error: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"[API_REQUEST] Response status: {e.response.status_code}")
                logger.error(f"[API_REQUEST] Response body: {e.response.text}")
            raise
    
    def create_dq_dashboard(
        self, 
        job_id: int,
        project_name: str,
        job_name: str,
        execution_id: int = None,
        catalog: Optional[str] = None,
        results_schema: Optional[str] = None,
        jobs_schema: Optional[str] = None,
        owner_email: str = None
    ) -> Dict[str, Any]:
        """
        Create a Databricks BI dashboard for a DQ job that completed successfully
        
        Args:
            job_id: Database job ID
            project_name: Project name (for table naming)
            job_name: Job name (for table naming)
            execution_id: Execution ID (optional, for linking dashboard to specific run)
            catalog: Databricks catalog name
            results_schema: Schema containing DQ results
            
        Returns:
            Dict with dashboard creation status and URL
        """
        catalog = catalog or os.getenv("UC_CATALOG", "")
        results_schema = results_schema or os.getenv("UC_RESULTS_SCHEMA", "db_gdm_dq_results")
        jobs_schema = jobs_schema or os.getenv("UC_SCHEMA", "db_gdm_data_quality_app")

        logger.info(f"\n{'='*80}")
        logger.info(f"[CREATE_DASHBOARD] STARTING Dashboard Creation")
        logger.info(f"[CREATE_DASHBOARD] Job ID: {job_id}")
        logger.info(f"[CREATE_DASHBOARD] Execution ID: {execution_id}")
        logger.info(f"[CREATE_DASHBOARD] Project: {project_name}")
        logger.info(f"[CREATE_DASHBOARD] Job Name: {job_name}")
        logger.info(f"[CREATE_DASHBOARD] Catalog: {catalog}")
        logger.info(f"[CREATE_DASHBOARD] Results Schema: {results_schema}")
        logger.info(f"{'='*80}\n")
        
        try:
            # Get warehouse ID first (needed for queries)
            logger.info("[CREATE_DASHBOARD] Step 1: Getting SQL warehouse...")
            warehouse_id = self._get_sql_warehouse()
            if not warehouse_id:
                return {
                    'status': 'error',
                    'message': 'No SQL warehouse available'
                }
            logger.info(f"[CREATE_DASHBOARD] ✅ Using SQL warehouse: {warehouse_id}")
            
            # Get quality thresholds from job configuration
            logger.info("[CREATE_DASHBOARD] Step 1.5: Fetching quality thresholds...")
            thresholds = self._get_job_thresholds(job_id, catalog, jobs_schema, warehouse_id)
            logger.info(f"[CREATE_DASHBOARD] ✅ Thresholds: OK={thresholds['ok_threshold']}, Warning={thresholds['warning_threshold']}")
            
            # Construct table names from job parameters (sanitize to avoid invalid characters)
            logger.info("[CREATE_DASHBOARD] Step 2: Constructing table names...")
            logger.info(f"[CREATE_DASHBOARD] Project: {project_name}, Job: {job_name}")
            
            # Build table names from project + job (raw names stored in DB)
            sanitized_project = self._sanitize_name(project_name)
            sanitized_job = self._sanitize_name(job_name)
            logger.info(f"[CREATE_DASHBOARD] Sanitized names: project={sanitized_project}, job={sanitized_job}")
            
            summary_columns_table = f"{catalog}.{results_schema}.dq_{sanitized_project}_{sanitized_job}_summary_columns"
            summary_dataset_table = f"{catalog}.{results_schema}.dq_{sanitized_project}_{sanitized_job}_summary_dataset"
            
            logger.info(f"[CREATE_DASHBOARD] ✅ Table names constructed:")
            logger.info(f"  - Summary columns: {summary_columns_table}")
            logger.info(f"  - Summary dataset: {summary_dataset_table}")
            
            # Create dashboard with Lakeview API
            # Create dashboard name from project and job
            dashboard_name = f"DQ_Dashboard_{project_name}_{job_name}".replace(' ', '_').replace(':', '_').replace('-', '_')
            logger.info(f"[CREATE_DASHBOARD] Step 3: Creating Lakeview dashboard '{dashboard_name}'...")
            
            # Build complete dashboard definition for Lakeview
            logger.info(f"[CREATE_DASHBOARD] Building dashboard with tables:")
            logger.info(f"[CREATE_DASHBOARD]   Columns: {summary_columns_table}")
            logger.info(f"[CREATE_DASHBOARD]   Dataset: {summary_dataset_table}")
            
            dashboard_definition = self._build_lakeview_dashboard(
                dashboard_name=dashboard_name,
                summary_columns_table=summary_columns_table,
                summary_dataset_table=summary_dataset_table,
                warehouse_id=warehouse_id,
                thresholds=thresholds,
                project_name=project_name,
                job_name=job_name
            )
            
            logger.info(f"[CREATE_DASHBOARD] Dashboard definition built, creating/updating dashboard...")
            logger.info(f"[CREATE_DASHBOARD] Owner email: {owner_email}")
            dashboard = self._create_lakeview_dashboard(dashboard_name, dashboard_definition, warehouse_id, job_id, owner_email=owner_email)
            dashboard_id = dashboard.get('dashboard_id') or dashboard.get('id')
            
            logger.info(f"[CREATE_DASHBOARD] ✅ Dashboard created with ID: {dashboard_id}")
            
            # Build published dashboard URL (opens directly in published view, no permission issues)
            # Extract workspace ID from host: adb-7405608753408268.8.azuredatabricks.net -> 7405608753408268
            import re as _re
            _ws_match = _re.search(r'adb-(\d+)\.', self.host)
            _workspace_id = _ws_match.group(1) if _ws_match else ''
            if _workspace_id:
                dashboard_url = f"https://{self.host}/dashboardsv3/{dashboard_id}/published/pages/DQ_Results?o={_workspace_id}"
            else:
                dashboard_url = f"https://{self.host}/sql/dashboardsv3/{dashboard_id}"
            
            logger.info(f"\n{'='*80}")
            logger.info(f"[CREATE_DASHBOARD] 🎉 SUCCESS! Dashboard created")
            logger.info(f"[CREATE_DASHBOARD] Dashboard ID: {dashboard_id}")
            logger.info(f"[CREATE_DASHBOARD] Dashboard URL: {dashboard_url}")
            logger.info(f"{'='*80}\n")
            
            return {
                'status': 'success',
                'dashboard_id': dashboard_id,
                'dashboard_url': dashboard_url,
                'dashboard_name': dashboard_name,
                'execution_id': execution_id,
                'message': f'Dashboard created successfully'
            }
            
        except Exception as e:
            logger.error(f"\n{'='*80}")
            logger.error(f"[CREATE_DASHBOARD] ❌ FAILED: {str(e)}")
            logger.error(f"[CREATE_DASHBOARD] Error type: {type(e).__name__}")
            logger.error(f"[CREATE_DASHBOARD] Job ID: {job_id}, Execution ID: {execution_id}")
            logger.error(f"{'='*80}\n")
            logger.error(f"[CREATE_DASHBOARD] Full traceback:", exc_info=True)
            return {
                'status': 'error',
                'message': f'Failed to create dashboard: {str(e)}',
                'error_type': type(e).__name__
            }
    
    def _get_sql_warehouse(self) -> Optional[str]:
        """Get the first available SQL warehouse"""
        try:
            logger.info("[WAREHOUSE] Fetching SQL warehouses...")
            response = self._make_api_request('GET', '/api/2.0/sql/warehouses')
            warehouses = response.get('warehouses', [])
            logger.info(f"[WAREHOUSE] Found {len(warehouses)} warehouse(s)")
            
            if warehouses:
                warehouse_id = warehouses[0].get('id')
                warehouse_name = warehouses[0].get('name', 'Unknown')
                warehouse_state = warehouses[0].get('state', 'Unknown')
                logger.info(f"[WAREHOUSE] ✅ Using warehouse:")
                logger.info(f"  ID: {warehouse_id}")
                logger.info(f"  Name: {warehouse_name}")
                logger.info(f"  State: {warehouse_state}")
                return warehouse_id
            
            logger.warning("[WAREHOUSE] ⚠️ No warehouses found!")
            logger.warning("[WAREHOUSE] Please create a SQL warehouse in Databricks")
            return None
        except Exception as e:
            logger.error(f"[WAREHOUSE] ❌ Error getting SQL warehouse: {str(e)}")
            logger.error(f"[WAREHOUSE] Exception type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            return None
    
    def _validate_queries(self, queries: Dict[str, str]) -> None:
        """Raise ValueError if any query in the dict is empty or blank."""
        for name, text in queries.items():
            if not text or not text.strip():
                logger.error(f"[BUILD_LAKEVIEW] ❌ Query '{name}' is empty")
                raise ValueError(f"Query '{name}' is empty")
            logger.info(f"[BUILD_LAKEVIEW] ✅ {name} validated ({len(text)} chars)")

    def _build_lakeview_dashboard(self, dashboard_name: str, summary_columns_table: str,
                                   summary_dataset_table: str, warehouse_id: str,
                                   thresholds: Dict[str, float],
                                   project_name: str = '', job_name: str = '') -> Dict[str, Any]:
        """Build Lakeview dashboard definition with queries and widgets following Databricks format"""
        logger.info(f"[BUILD_LAKEVIEW] Building dashboard definition...")
        logger.info(f"[BUILD_LAKEVIEW] Dashboard name: {dashboard_name}")
        logger.info(f"[BUILD_LAKEVIEW] Summary columns table: {summary_columns_table}")
        logger.info(f"[BUILD_LAKEVIEW] Summary dataset table: {summary_dataset_table}")
        
        # Get available dimensions
        dimensions = self._get_dimensions(summary_dataset_table, warehouse_id)
        logger.info(f"[BUILD_LAKEVIEW] Dimensions found: {dimensions}")
        
        # Step 1: Build queries
        logger.info(f"[BUILD_LAKEVIEW] Step 1: Building SQL queries...")
        ok_query = f"SELECT COUNT(*) as ok_count\nFROM {summary_columns_table}\nWHERE status = 'OK'"
        warning_query = f"SELECT COUNT(*) as warning_count\nFROM {summary_columns_table}\nWHERE status = 'Warning'"
        error_query = f"SELECT COUNT(*) as error_count\nFROM {summary_columns_table}\nWHERE status = 'KO'"
        total_columns_query = f"SELECT COUNT(DISTINCT column_name) as total_columns\nFROM {summary_columns_table}"
        total_rows_query = f"SELECT MAX(total_rows) as total_rows\nFROM {summary_columns_table}"
        overall_score_query = f"SELECT ROUND(AVG(dataset_score)/100, 4) as overall_score\nFROM {summary_dataset_table}\nWHERE check_type != 'overall'"
        
        logger.info(f"[BUILD_LAKEVIEW] OK Query: {ok_query}")
        logger.info(f"[BUILD_LAKEVIEW] Warning Query: {warning_query}")
        logger.info(f"[BUILD_LAKEVIEW] Error Query: {error_query}")
        logger.info(f"[BUILD_LAKEVIEW] Total Columns Query: {total_columns_query}")
        logger.info(f"[BUILD_LAKEVIEW] Total Rows Query: {total_rows_query}")
        logger.info(f"[BUILD_LAKEVIEW] Overall Score Query: {overall_score_query}")
        
        # Build dimension queries
        dimension_queries = {}
        dimension_detail_queries = {}
        for dim in dimensions:
            dimension_queries[dim] = f"SELECT ROUND(dataset_score/100, 4) as dataset_score, dataset_status\nFROM {summary_dataset_table}\nWHERE check_type = '{dim}'"
            dimension_detail_queries[dim] = f"SELECT column_name, ROUND(score, 2) as score, status, valid_count, invalid_count, null_count\nFROM {summary_columns_table}\nWHERE check_type = '{dim}'\nORDER BY score ASC, column_name ASC"
            logger.info(f"[BUILD_LAKEVIEW] Dimension '{dim}' score query: {dimension_queries[dim]}")
        
        # Step 2: Validate queries are non-empty
        logger.info(f"[BUILD_LAKEVIEW] Step 2: Validating queries...")
        self._validate_queries({
            "ok_query": ok_query,
            "warning_query": warning_query,
            "error_query": error_query,
            "total_columns_query": total_columns_query,
            "total_rows_query": total_rows_query,
            "overall_score_query": overall_score_query,
        })
        
        # Step 3: Build dashboard structure following Databricks Lakeview format
        logger.info(f"[BUILD_LAKEVIEW] Step 3: Building dashboard structure...")
        
        # Build datasets with queryLines format (split by newlines)
        dataset_counter = 1
        dashboard_def = {
            "datasets": [
                {
                    "name": f"dataset_{dataset_counter}",
                    "displayName": "OK Columns",
                    "queryLines": [line + "\n" for line in ok_query.split("\n")]
                },
                {
                    "name": f"dataset_{dataset_counter + 1}",
                    "displayName": "Warning Columns",
                    "queryLines": [line + "\n" for line in warning_query.split("\n")]
                },
                {
                    "name": f"dataset_{dataset_counter + 2}",
                    "displayName": "Error Columns",
                    "queryLines": [line + "\n" for line in error_query.split("\n")]
                },
                {
                    "name": f"dataset_{dataset_counter + 3}",
                    "displayName": "Total Columns",
                    "queryLines": [line + "\n" for line in total_columns_query.split("\n")]
                },
                {
                    "name": f"dataset_{dataset_counter + 4}",
                    "displayName": "Total Rows",
                    "queryLines": [line + "\n" for line in total_rows_query.split("\n")]
                },
                {
                    "name": f"dataset_{dataset_counter + 5}",
                    "displayName": "Overall Score",
                    "queryLines": [line + "\n" for line in overall_score_query.split("\n")]
                }
            ],
            "pages": [
                {
                    "name": "DQ_Results",
                    "displayName": "Data Quality Results",
                    "layout": [],
                    "pageType": "PAGE_TYPE_CANVAS",
                    "layoutVersion": "GRID_V1"
                }
            ]
        }
        
        dataset_counter = 7  # Start from 7 for dimension datasets
        
        # Add dimension datasets
        for dim in dimensions:
            dashboard_def["datasets"].append({
                "name": f"dataset_{dataset_counter}",
                "displayName": f"{dim.capitalize()} Score",
                "queryLines": [line + "\n" for line in dimension_queries[dim].split("\n")]
            })
            dataset_counter += 1
            
            dashboard_def["datasets"].append({
                "name": f"dataset_{dataset_counter}",
                "displayName": f"{dim.capitalize()} Details",
                "queryLines": [line + "\n" for line in dimension_detail_queries[dim].split("\n")]
            })
            dataset_counter += 1

        # Add column status list datasets for bottom section.
        # IMPORTANT: keep the exact per-row status from summary_columns so that each
        # column + dimension uses the same status as the source table, rather than
        # collapsing multiple checks into a single column-level status.
        # DISTINCT column_name: a column can be OK/Warning/KO in several dimensions, so
        # without DISTINCT the same column would be repeated once per check_type.
        ok_list_dataset_name = f"dataset_{dataset_counter}"
        dashboard_def["datasets"].append({
            "name": ok_list_dataset_name,
            "displayName": "OK Columns List",
            "queryLines": [line + "\n" for line in (
                f"SELECT DISTINCT column_name\n"
                f"FROM {summary_columns_table}\n"
                f"WHERE status = 'OK'\n"
                f"ORDER BY column_name"
            ).split("\n")]
        })
        dataset_counter += 1
        warning_list_dataset_name = f"dataset_{dataset_counter}"
        dashboard_def["datasets"].append({
            "name": warning_list_dataset_name,
            "displayName": "Warning Columns List",
            "queryLines": [line + "\n" for line in (
                f"SELECT DISTINCT column_name\n"
                f"FROM {summary_columns_table}\n"
                f"WHERE status = 'Warning'\n"
                f"ORDER BY column_name"
            ).split("\n")]
        })
        dataset_counter += 1
        ko_list_dataset_name = f"dataset_{dataset_counter}"
        dashboard_def["datasets"].append({
            "name": ko_list_dataset_name,
            "displayName": "KO Columns List",
            "queryLines": [line + "\n" for line in (
                f"SELECT DISTINCT column_name\n"
                f"FROM {summary_columns_table}\n"
                f"WHERE status = 'KO'\n"
                f"ORDER BY column_name"
            ).split("\n")]
        })
        dataset_counter += 1

        logger.info(f"[BUILD_LAKEVIEW] Created {len(dashboard_def['datasets'])} datasets")

        # Collect live metrics for Quality Summary section
        logger.info(f"[BUILD_LAKEVIEW] Collecting metrics for Quality Summary...")
        dashboard_metrics = self._collect_dashboard_metrics(
            summary_columns_table=summary_columns_table,
            summary_dataset_table=summary_dataset_table,
            warehouse_id=warehouse_id,
            thresholds=thresholds
        )

        # Build widgets
        widget_counter = 1
        layouts = []

        # Left panel (top): Logo widget (resized to 5 cols, 2 rows)
        layouts.append({
            "widget": {
                "name": f"widget_{widget_counter}",
                "multilineTextboxSpec": {
                    "lines": [
                        """<span style="text-align:center;display:block;"><img src="data:image/png;base64,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" style="max-width:150px;height:auto;" /></span>"""
                    ]
                }
            },
            "position": {
                "x": 0,
                "y": 0,
                "width": 5,
                "height": 5
            }
        })
        widget_counter += 1

        # Left panel (bottom): Threshold legend
        left_panel_md = self._generate_left_panel_markdown(
            project_name=project_name,
            job_name=job_name,
            metrics=dashboard_metrics,
            thresholds=thresholds
        )
        layouts.append({
            "widget": {
                "name": f"widget_{widget_counter}",
                "multilineTextboxSpec": {
                    "lines": [left_panel_md]
                }
            },
            "position": {
                "x": 0,
                "y": 5,
                "width": 3,
                "height": 4
            }
        })
        widget_counter += 1

        # Quality Summary section removed per user request
        # quality_summary_md = self._generate_quality_summary_markdown(...)

        # Row 1: Summary counters (top-right area)
        # Overall Score card
        layouts.append({
            "widget": {
                "name": f"widget_{widget_counter}",
                "queries": [{
                    "name": "main_query",
                    "query": {
                        "datasetName": "dataset_6",
                        "fields": [{"name": "overall_score", "expression": "`overall_score`"}],
                        "disaggregated": True
                    }
                }],
                "spec": {
                    "version": 2,
                    "frame": {
                        "title": "Overall Score",
                        "showTitle": True,
                        "description": "Average quality score across all analyzed columns and dimensions",
                        "showDescription": True
                    },
                    "widgetType": "counter",
                    "encodings": {
                        "value": {
                            "fieldName": "overall_score",
                            "displayName": "Overall Score (%)",
                            "format": {
                                "type": "number-percent",
                                "decimalPlaces": {
                                    "type": "max",
                                    "places": 2
                                }
                            },
                            "style": {
                                "rules": [
                                    {
                                        "condition": {
                                            "operand": {"type": "data-value", "value": str(thresholds['ok_threshold'] / 100)},
                                            "operator": ">="
                                        },
                                        "color": {"themeColorType": "visualizationColors", "position": 7}
                                    },
                                    {
                                        "condition": {
                                            "operand": {"type": "data-value", "value": str(thresholds['warning_threshold'] / 100)},
                                            "operator": ">="
                                        },
                                        "color": "#FFC200"
                                    },
                                    {
                                        "condition": {
                                            "operand": {"type": "data-value", "value": str(thresholds['warning_threshold'] / 100)},
                                            "operator": "<"
                                        },
                                        "color": {"themeColorType": "visualizationColors", "position": 8}
                                    }
                                ]
                            }
                        }
                    }
                }
            },
            "position": {"x": 5, "y": 0, "width": 7, "height": 3}
        })
        widget_counter += 1

        # Total Rows card
        layouts.append({
            "widget": {
                "name": f"widget_{widget_counter}",
                "queries": [{
                    "name": "main_query",
                    "query": {
                        "datasetName": "dataset_5",
                        "fields": [{"name": "total_rows", "expression": "`total_rows`"}],
                        "disaggregated": True
                    }
                }],
                "spec": {
                    "version": 2,
                    "frame": {
                        "title": "Total Analyzed Rows",
                        "showTitle": True,
                        "description": "Total number of rows in the analyzed dataset",
                        "showDescription": True
                    },
                    "widgetType": "counter",
                    "encodings": {"value": {"fieldName": "total_rows"}}
                }
            },
            "position": {"x": 3, "y": 5, "width": 2, "height": 2}
        })
        widget_counter += 1

        # Total Columns card
        layouts.append({
            "widget": {
                "name": f"widget_{widget_counter}",
                "queries": [{
                    "name": "main_query",
                    "query": {
                        "datasetName": "dataset_4",
                        "fields": [{"name": "sum(total_columns)", "expression": "SUM(`total_columns`)"}],
                        "disaggregated": False
                    }
                }],
                "spec": {
                    "version": 2,
                    "frame": {
                        "title": "Total Analyzed Columns",
                        "showTitle": True,
                        "description": "Total number of columns analyzed in the dataset",
                        "showDescription": True
                    },
                    "widgetType": "counter",
                    "encodings": {"value": {"fieldName": "sum(total_columns)"}}
                }
            },
            "position": {"x": 3, "y": 7, "width": 2, "height": 2}
        })
        widget_counter += 1

        # OK columns card
        layouts.append({
            "widget": {
                "name": f"widget_{widget_counter}",
                "queries": [{
                    "name": "main_query",
                    "query": {
                        "datasetName": "dataset_1",
                        "fields": [{"name": "sum(ok_count)", "expression": "SUM(`ok_count`)"}],
                        "disaggregated": False
                    }
                }],
                "spec": {
                    "version": 2,
                    "frame": {
                        "title": "OK",
                        "showTitle": True,
                        "headerAlignment": "center",
                        "description": "Number of columns with quality score >= " + str(thresholds['ok_threshold']) + "%",
                        "showDescription": True
                    },
                    "widgetType": "counter",
                    "encodings": {
                        "value": {
                            "fieldName": "sum(ok_count)",
                            "style": {
                                "color": {
                                    "themeColorType": "visualizationColors",
                                    "position": 7
                                }
                            }
                        }
                    }
                }
            },
            "position": {"x": 5, "y": 3, "width": 7, "height": 2}
        })
        widget_counter += 1

        # Warning columns card
        layouts.append({
            "widget": {
                "name": f"widget_{widget_counter}",
                "queries": [{
                    "name": "main_query",
                    "query": {
                        "datasetName": "dataset_2",
                        "fields": [{"name": "sum(warning_count)", "expression": "SUM(`warning_count`)"}],
                        "disaggregated": False
                    }
                }],
                "spec": {
                    "version": 2,
                    "frame": {
                        "title": "To monitor",
                        "showTitle": True,
                        "headerAlignment": "center",
                        "description": "Columns with quality score between " + str(thresholds['warning_threshold']) + "% and " + str(thresholds['ok_threshold']) + "%",
                        "showDescription": True
                    },
                    "widgetType": "counter",
                    "encodings": {
                        "value": {
                            "fieldName": "sum(warning_count)",
                            "style": {
                                "color": "#FFC200"
                            }
                        }
                    }
                }
            },
            "position": {"x": 5, "y": 5, "width": 7, "height": 2}
        })
        widget_counter += 1

        # Error columns card
        layouts.append({
            "widget": {
                "name": f"widget_{widget_counter}",
                "queries": [{
                    "name": "main_query",
                    "query": {
                        "datasetName": "dataset_3",
                        "fields": [{"name": "sum(error_count)", "expression": "SUM(`error_count`)"}],
                        "disaggregated": False
                    }
                }],
                "spec": {
                    "version": 2,
                    "frame": {
                        "title": "Error",
                        "showTitle": True,
                        "headerAlignment": "center",
                        "description": "Number of columns with quality score < " + str(thresholds['warning_threshold']) + "%",
                        "showDescription": True
                    },
                    "widgetType": "counter",
                    "encodings": {
                        "value": {
                            "fieldName": "sum(error_count)",
                            "style": {
                                "color": {
                                    "themeColorType": "visualizationColors",
                                    "position": 8
                                }
                            }
                        }
                    }
                }
            },
            "position": {"x": 5, "y": 7, "width": 7, "height": 2}
        })
        widget_counter += 1

        # Add dimension widgets: score counter + details table
        current_row = 9  # Start below the header counters row (y=9)
        dataset_idx = 7
        
        for dim in dimensions:
            # Dimension score counter with conditional coloring and percentage format
            layouts.append({
                "widget": {
                    "name": f"widget_{widget_counter}",
                    "queries": [{
                        "name": "main_query",
                        "query": {
                            "datasetName": f"dataset_{dataset_idx}",
                            "fields": [{"name": "dataset_score", "expression": "`dataset_score`"}],
                            "disaggregated": True
                        }
                    }],
                    "spec": {
                        "version": 2,
                        "frame": {
                            "title": f"{dim.capitalize()} Score",
                            "showTitle": True,
                            "description": f"Average {dim} quality score across all columns",
                            "showDescription": True
                        },
                        "widgetType": "counter",
                        "encodings": {
                            "value": {
                                "fieldName": "dataset_score",
                                "displayName": f"{dim.capitalize()} (%)",
                                "format": {
                                    "type": "number-percent",
                                    "decimalPlaces": {
                                        "type": "max",
                                        "places": 2
                                    }
                                },
                                "style": {
                                    "rules": [
                                        {
                                            "condition": {
                                                "operand": {"type": "data-value", "value": str(thresholds['ok_threshold'] / 100)},
                                                "operator": ">="
                                            },
                                            "color": {
                                                "themeColorType": "visualizationColors",
                                                "position": 7
                                            }
                                        },
                                        {
                                            "condition": {
                                                "operand": {"type": "data-value", "value": str(thresholds['warning_threshold'] / 100)},
                                                "operator": ">="
                                            },
                                            "color": "#FFC200"
                                        },
                                        {
                                            "condition": {
                                                "operand": {"type": "data-value", "value": str(thresholds['warning_threshold'] / 100)},
                                                "operator": "<"
                                            },
                                            "color": {
                                                "themeColorType": "visualizationColors",
                                                "position": 8
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    }
                },
                "position": {"x": 0, "y": current_row, "width": 3, "height": 4}
            })
            widget_counter += 1
            dataset_idx += 1
            
            # Dimension details table with column styling (removed total_rows)
            layouts.append({
                "widget": {
                    "name": f"widget_{widget_counter}",
                    "queries": [{
                        "name": "main_query",
                        "query": {
                            "datasetName": f"dataset_{dataset_idx}",
                            "fields": [
                                {"name": "column_name", "expression": _COLUMN_NAME_EXPR},
                                {"name": "score", "expression": "`score`"},
                                {"name": "status", "expression": "`status`"},
                                {"name": "valid_count", "expression": "`valid_count`"},
                                {"name": "invalid_count", "expression": "`invalid_count`"},
                                {"name": "null_count", "expression": "`null_count`"}
                            ],
                            "disaggregated": True
                        }
                    }],
                    "spec": {
                        "version": 2,
                        "frame": {
                            "title": f"{dim.capitalize()} - Column Details",
                            "showTitle": True,
                            "showDescription": False
                        },
                        "widgetType": "table",
                        "encodings": {
                            "columns": [
                                {"fieldName": "column_name"},
                                {
                                    "fieldName": "score",
                                    "style": {
                                        "type": "basic",
                                        # Color driven by "status" (sourceField), not by a fixed numeric
                                        # threshold, so this cell always matches the real per-row status
                                        # even when a custom Step 2 threshold is used for this column.
                                        "rules": [
                                            {
                                                "condition": {
                                                    "operand": {"type": "data-value", "value": "OK"},
                                                    "operator": "="
                                                },
                                                "sourceField": "status",
                                                "backgroundColor": {
                                                    "themeColorType": "visualizationColors",
                                                    "position": 7
                                                },
                                                "foregroundColor": {
                                                    "themeColorType": "canvasBackgroundColor"
                                                }
                                            },
                                            {
                                                "condition": {
                                                    "operand": {"type": "data-value", "value": "Warning"},
                                                    "operator": "="
                                                },
                                                "sourceField": "status",
                                                "backgroundColor": "#FFC200",
                                                "foregroundColor": {
                                                    "themeColorType": "canvasBackgroundColor"
                                                }
                                            },
                                            {
                                                "condition": {
                                                    "operand": {"type": "data-value", "value": "KO"},
                                                    "operator": "="
                                                },
                                                "sourceField": "status",
                                                "backgroundColor": {
                                                    "themeColorType": "visualizationColors",
                                                    "position": 8
                                                },
                                                "foregroundColor": {
                                                    "themeColorType": "canvasBackgroundColor"
                                                }
                                            }
                                        ]
                                    }
                                },
                                {
                                    "fieldName": "status",
                                    "contentAlignment": "center",
                                    "style": {
                                        "type": "basic",
                                        "rules": [
                                            {
                                                "condition": {
                                                    "operand": {"type": "data-value", "value": "OK"},
                                                    "operator": "="
                                                },
                                                "backgroundColor": {
                                                    "themeColorType": "visualizationColors",
                                                    "position": 7
                                                },
                                                "foregroundColor": {
                                                    "themeColorType": "canvasBackgroundColor"
                                                }
                                            },
                                            {
                                                "condition": {
                                                    "operand": {"type": "data-value", "value": "Warning"},
                                                    "operator": "="
                                                },
                                                "backgroundColor": "#FFC200",
                                                "foregroundColor": {
                                                    "themeColorType": "canvasBackgroundColor"
                                                }
                                            },
                                            {
                                                "condition": {
                                                    "operand": {"type": "data-value", "value": "KO"},
                                                    "operator": "="
                                                },
                                                "backgroundColor": {
                                                    "themeColorType": "visualizationColors",
                                                    "position": 8
                                                },
                                                "foregroundColor": {
                                                    "themeColorType": "canvasBackgroundColor"
                                                }
                                            }
                                        ]
                                    }
                                },
                                {"fieldName": "valid_count"},
                                {"fieldName": "invalid_count"},
                                {"fieldName": "null_count"}
                            ]
                        }
                    }
                },
                "position": {"x": 3, "y": current_row, "width": 9, "height": 4}
            })
            widget_counter += 1
            dataset_idx += 1
            current_row += 4

        # Bottom section: Column quality lists (3 side-by-side tables)
        bottom_row = current_row
        col_width = 4

        # OK columns list (green)
        layouts.append({
            "widget": {
                "name": f"widget_{widget_counter}",
                "queries": [{
                    "name": "main_query",
                    "query": {
                        "datasetName": ok_list_dataset_name,
                        "fields": [{"name": "column_name", "expression": _COLUMN_NAME_EXPR}],
                        "disaggregated": True
                    }
                }],
                "spec": {
                    "version": 2,
                    "frame": {
                        "title": "\U0001f7e2 Columns with Good Quality",
                        "showTitle": True,
                        "showDescription": False
                    },
                    "widgetType": "table",
                    "encodings": {
                        "columns": [{
                            "fieldName": "column_name",
                            "displayName": _COLUMN_NAME_DISPLAY,
                            "style": {
                                "type": "basic",
                                "rules": [{
                                    "condition": {
                                        "operand": {"type": "data-value", "value": ""},
                                        "operator": "!="
                                    },
                                    "backgroundColor": {"themeColorType": "visualizationColors", "position": 7},
                                    "foregroundColor": {"themeColorType": "canvasBackgroundColor"}
                                }]
                            }
                        }]
                    }
                }
            },
            "position": {"x": 0, "y": bottom_row, "width": col_width, "height": 6}
        })
        widget_counter += 1

        # Warning columns list (orange)
        layouts.append({
            "widget": {
                "name": f"widget_{widget_counter}",
                "queries": [{
                    "name": "main_query",
                    "query": {
                        "datasetName": warning_list_dataset_name,
                        "fields": [{"name": "column_name", "expression": _COLUMN_NAME_EXPR}],
                        "disaggregated": True
                    }
                }],
                "spec": {
                    "version": 2,
                    "frame": {
                        "title": "\U0001f7e1 Columns to Keep Monitoring",
                        "showTitle": True,
                        "showDescription": False
                    },
                    "widgetType": "table",
                    "encodings": {
                        "columns": [{
                            "fieldName": "column_name",
                            "displayName": _COLUMN_NAME_DISPLAY,
                            "style": {
                                "type": "basic",
                                "rules": [{
                                    "condition": {
                                        "operand": {"type": "data-value", "value": ""},
                                        "operator": "!="
                                    },
                                    "backgroundColor": "#FFC200",
                                    "foregroundColor": {"themeColorType": "canvasBackgroundColor"}
                                }]
                            }
                        }]
                    }
                }
            },
            "position": {"x": col_width, "y": bottom_row, "width": col_width, "height": 6}
        })
        widget_counter += 1

        # KO columns list (red)
        layouts.append({
            "widget": {
                "name": f"widget_{widget_counter}",
                "queries": [{
                    "name": "main_query",
                    "query": {
                        "datasetName": ko_list_dataset_name,
                        "fields": [{"name": "column_name", "expression": _COLUMN_NAME_EXPR}],
                        "disaggregated": True
                    }
                }],
                "spec": {
                    "version": 2,
                    "frame": {
                        "title": "\U0001f534 Columns to Remediate in Priority",
                        "showTitle": True,
                        "showDescription": False
                    },
                    "widgetType": "table",
                    "encodings": {
                        "columns": [{
                            "fieldName": "column_name",
                            "displayName": _COLUMN_NAME_DISPLAY,
                            "style": {
                                "type": "basic",
                                "rules": [{
                                    "condition": {
                                        "operand": {"type": "data-value", "value": ""},
                                        "operator": "!="
                                    },
                                    "backgroundColor": {"themeColorType": "visualizationColors", "position": 8},
                                    "foregroundColor": {"themeColorType": "canvasBackgroundColor"}
                                }]
                            }
                        }]
                    }
                }
            },
            "position": {"x": col_width * 2, "y": bottom_row, "width": col_width, "height": 6}
        })
        widget_counter += 1

        dashboard_def["pages"][0]["layout"] = layouts
        logger.info(f"[BUILD_LAKEVIEW] Created {len(layouts)} widgets")
        
        # Step 4: Final validation
        logger.info(f"[BUILD_LAKEVIEW] Step 4: Final validation...")
        logger.info(f"[BUILD_LAKEVIEW] ✅ Built {len(dashboard_def['datasets'])} datasets")
        logger.info(f"[BUILD_LAKEVIEW] ✅ Built {len(dashboard_def['pages'][0]['layout'])} widgets")
        
        for ds in dashboard_def["datasets"]:
            if not ds.get("queryLines"):
                error_msg = f"Dataset '{ds.get('name')}' has no queryLines"
                logger.error(f"[BUILD_LAKEVIEW] ❌ {error_msg}")
                raise ValueError(error_msg)
            logger.info(f"[BUILD_LAKEVIEW] ✅ Dataset '{ds['name']}' has {len(ds['queryLines'])} query lines")
        
        for idx, layout_item in enumerate(dashboard_def['pages'][0]['layout']):
            widget = layout_item.get("widget", {})
            widget_name = widget.get("name", f"widget_{idx+1}")
            
            # Skip validation for textbox widgets (they don't have queries)
            if widget.get("multilineTextboxSpec"):
                logger.info(f"[BUILD_LAKEVIEW] ✅ Widget '{widget_name}' is a textbox widget")
                continue
            
            queries = widget.get("queries", [])
            if not queries:
                error_msg = f"Widget '{widget_name}' has no queries"
                logger.error(f"[BUILD_LAKEVIEW] ❌ {error_msg}")
                raise ValueError(error_msg)
            
            main_query = queries[0].get("query", {})
            dataset_name = main_query.get("datasetName")
            if not dataset_name:
                error_msg = f"Widget '{widget_name}' has no datasetName"
                logger.error(f"[BUILD_LAKEVIEW] ❌ {error_msg}")
                raise ValueError(error_msg)
            
            logger.info(f"[BUILD_LAKEVIEW] ✅ Widget '{widget_name}' references dataset '{dataset_name}'")
        
        logger.info(f"[BUILD_LAKEVIEW] ✅ Dashboard definition complete and validated")
        return dashboard_def
    
    def _get_current_user(self) -> str:
        """Return the userName (email) of the currently authenticated user."""
        try:
            result = self._make_api_request('GET', '/api/2.0/preview/scim/v2/Me')
            username = result.get('userName', '')
            if username:
                logger.info(f"[CURRENT_USER] Resolved current user: {username}")
                return username
        except Exception as e:
            logger.warning(f"[CURRENT_USER] Could not resolve current user via SCIM: {e}")
        return ''

    def _ensure_workspace_folder(self, path: str) -> bool:
        """Create a workspace folder (and all parents) if it does not already exist.
        Returns True if folder exists/was created, False if permission denied."""
        try:
            self._make_api_request('POST', '/api/2.0/workspace/mkdirs', {'path': path})
            logger.info(f"[WORKSPACE] Folder ensured: {path}")
            return True
        except Exception as e:
            logger.warning(f"[WORKSPACE] Could not create folder '{path}': {e}")
            return False

    def _publish_dashboard(self, dashboard_id: str, warehouse_id: str) -> None:
        """Publish a Lakeview dashboard so queries run with the SP owner's credentials.
        This allows any workspace user to view widgets without needing direct UC grants."""
        try:
            self._make_api_request(
                'POST',
                f'/api/2.0/lakeview/dashboards/{dashboard_id}/published',
                {'warehouse_id': warehouse_id, 'embed_credentials': True}
            )
            logger.info(f"[PUBLISH] ✅ Dashboard {dashboard_id} published (embed_credentials=True)")
        except Exception as e:
            logger.warning(f"[PUBLISH] ⚠️ Could not publish dashboard {dashboard_id} (non-blocking): {e}")

    def _resolve_parent_path(self, username: str) -> str:
        """Return the workspace folder path for the dashboard, falling back to /Shared if needed."""
        shared_path = '/Shared/data quality'
        if not username:
            self._ensure_workspace_folder(shared_path)
            logger.warning('[CREATE_LAKEVIEW] Falling back to /Shared/data quality (could not resolve user)')
            return shared_path
        user_path = f'/Users/{username}/data quality'
        if self._ensure_workspace_folder(user_path):
            logger.info(f'[CREATE_LAKEVIEW] Using user parent path: {user_path}')
            return user_path
        self._ensure_workspace_folder(shared_path)
        logger.warning(f'[CREATE_LAKEVIEW] No permission on user folder, falling back to: {shared_path}')
        return shared_path

    @staticmethod
    def _parse_http_error(e) -> tuple:
        """Return (error_code, error_body) extracted from an HTTPError response."""
        if not (hasattr(e, 'response') and e.response is not None):
            return '', ''
        error_body = e.response.text
        try:
            error_code = e.response.json().get('error_code', '')
        except Exception:
            error_code = ''
        return error_code, error_body

    @staticmethod
    def _is_already_exists_error(error_code: str, error_body: str, exc) -> bool:
        """Return True when the HTTP error indicates the dashboard already exists."""
        return (
            error_code in ('RESOURCE_ALREADY_EXISTS', 'ALREADY_EXISTS')
            or 'RESOURCE_ALREADY_EXISTS' in error_body
            or 'ALREADY_EXISTS' in error_body
            or 'already exists' in str(exc).lower()
        )

    def _resolve_existing_dashboard_id(self, job_id, error_body: str):
        """Find an existing dashboard ID via DB lookup → error-body regex (two patterns)."""
        import re
        if job_id:
            try:
                from database.repositories.job_repository import JobRepository
                existing = JobRepository.get_dashboards_for_job(job_id)
                if existing:
                    dashboard_id = existing[0].get('dashboard_id')
                    logger.info(f"[CREATE_LAKEVIEW] ✅ Found dashboard_id from dq_dashboards: {dashboard_id}")
                    return dashboard_id
                logger.info(f"[CREATE_LAKEVIEW] No entry in dq_dashboards for job_id={job_id}")
            except Exception as db_err:
                logger.warning(f"[CREATE_LAKEVIEW] Could not query dq_dashboards: {db_err}")
        # Fallback 1: path pattern in error body
        m = re.search(r'workspaces/\d+/dashboards/([a-f0-9]+)', error_body)
        if m:
            logger.info(f"[CREATE_LAKEVIEW] Found dashboard_id from error message: {m.group(1)}")
            return m.group(1)
        # Fallback 2: existing_node_id in error details JSON
        m2 = re.search(r'"existing_node_id"\s*:\s*"(\d+)"', error_body)
        if m2:
            logger.info(f"[CREATE_LAKEVIEW] Found dashboard_id from existing_node_id: {m2.group(1)}")
            return m2.group(1)
        return None

    def _handle_dashboard_already_exists(self, dashboard_name: str, definition: Dict[str, Any],
                                          warehouse_id: str, job_id, error_body: str) -> Dict[str, Any]:
        """Update an existing dashboard instead of creating a new one."""
        import json
        logger.warning(f"[CREATE_LAKEVIEW] Dashboard '{dashboard_name}' already exists, attempting update...")
        try:
            dashboard_id = self._resolve_existing_dashboard_id(job_id, error_body)
            if not dashboard_id:
                logger.error(f"[CREATE_LAKEVIEW] ❌ Could not find dashboard ID for '{dashboard_name}'")
                raise RuntimeError(f"Dashboard '{dashboard_name}' already exists but its ID could not be resolved")
            logger.info(f"[CREATE_LAKEVIEW] Updating dashboard {dashboard_id}...")
            self._make_api_request('PATCH', f'/api/2.0/lakeview/dashboards/{dashboard_id}',
                                   {'serialized_dashboard': json.dumps(definition), 'warehouse_id': warehouse_id})
            logger.info("[CREATE_LAKEVIEW] ✅ Dashboard updated successfully")
            self._publish_dashboard(dashboard_id, warehouse_id)
            return {'dashboard_id': dashboard_id, 'id': dashboard_id}
        except Exception as update_error:
            logger.error(f"[CREATE_LAKEVIEW] ❌ Failed to update existing dashboard: {str(update_error)}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    def _create_lakeview_dashboard(self, dashboard_name: str, definition: Dict[str, Any],
                                   warehouse_id: str, job_id: int = None, owner_email: str = None) -> Dict[str, Any]:
        """Create Lakeview dashboard with definition"""
        import json
        import requests

        logger.info(f"[CREATE_LAKEVIEW] Creating dashboard with Lakeview API...")
        logger.info(f"[CREATE_LAKEVIEW] Dashboard definition: {json.dumps(definition, indent=2)[:2000]}")

        username = owner_email or self._get_current_user()
        parent_path = self._resolve_parent_path(username)

        data = {
            'display_name': dashboard_name,
            'parent_path': parent_path,
            'serialized_dashboard': json.dumps(definition),
            'warehouse_id': warehouse_id,
        }

        try:
            result = self._make_api_request('POST', '/api/2.0/lakeview/dashboards', data)
            logger.info("[CREATE_LAKEVIEW] ✅ Dashboard created successfully")
            dashboard_id = result.get('dashboard_id') or result.get('id')
            if dashboard_id:
                self._publish_dashboard(dashboard_id, warehouse_id)
            return result
        except requests.exceptions.HTTPError as e:
            logger.error(f"[CREATE_LAKEVIEW] HTTP Error: {str(e)}")
            error_code, error_body = self._parse_http_error(e)
            if self._is_already_exists_error(error_code, error_body, e):
                return self._handle_dashboard_already_exists(dashboard_name, definition, warehouse_id, job_id, error_body)
            logger.error(f"[CREATE_LAKEVIEW] ❌ Failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"[CREATE_LAKEVIEW] ❌ Unexpected error: {str(e)}")
            raise
    
    def _get_job_thresholds(self, job_id: int, catalog: str, jobs_schema: str, warehouse_id: str) -> Dict[str, float]:
        """Get the Step 2 threshold configuration from dq_jobs."""
        try:
            query_sql = f"""
SELECT quality_config
FROM {catalog}.{jobs_schema}.dq_jobs
WHERE id = {job_id}
            """
            
            result = self._execute_query(query_sql, warehouse_id)
            data = result.get('data_array', [])
            
            if data and data[0] and data[0][0]:
                quality_config = data[0][0]
                if isinstance(quality_config, str):
                    quality_config = json.loads(quality_config)
                thresholds_config = quality_config.get('thresholds', {})
                logger.info("[THRESHOLDS] Retrieved Step 2 thresholds from dq_jobs.quality_config")
                return {
                    'ok_threshold': 100.0,
                    'warning_threshold': 98.0,
                    'step2_thresholds': thresholds_config
                }
            else:
                logger.warning("[THRESHOLDS] No quality_config found in dq_jobs, using defaults")
                return {'ok_threshold': 100.0, 'warning_threshold': 98.0, 'step2_thresholds': {}}
                
        except Exception as e:
            logger.warning(f"[THRESHOLDS] Error getting thresholds: {e}, using defaults")
            return {'ok_threshold': 100.0, 'warning_threshold': 98.0, 'step2_thresholds': {}}
    
    def _get_dimensions(self, summary_dataset_table: str, warehouse_id: Optional[str]) -> List[str]:
        """Get list of quality dimensions from summary_dataset table"""
        try:
            if not warehouse_id:
                logger.warning("[DIMENSIONS] No warehouse, using defaults")
                return ['completeness', 'validity', 'consistency', 'uniqueness']
            
            # Query to get dimensions
            query_sql = f"""
SELECT DISTINCT check_type
FROM {summary_dataset_table}
WHERE check_type != 'overall'
ORDER BY check_type
            """
            
            result = self._execute_query(query_sql, warehouse_id)
            dimensions = [row[0] for row in result.get('data_array', [])]
            logger.info(f"[DIMENSIONS] Found dimensions: {dimensions}")
            return dimensions if dimensions else ['completeness', 'validity', 'consistency', 'uniqueness']
            
        except Exception as e:
            logger.warning(f"[DIMENSIONS] Error getting dimensions: {e}, using defaults")
            return ['completeness', 'validity', 'consistency', 'uniqueness']
    
    def _execute_query(self, query_sql: str, warehouse_id: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute a SQL query and wait for results"""
        import time
        
        logger.info(f"[EXECUTE_QUERY] Executing SQL query:")
        logger.info(f"  Warehouse: {warehouse_id}")
        logger.info(f"  Query: {query_sql[:200]}...")
        
        # Start query execution
        data = {
            'warehouse_id': warehouse_id,
            'statement': query_sql,
            'wait_timeout': f'{timeout}s'
        }
        
        try:
            response = self._make_api_request('POST', '/api/2.0/sql/statements', data)
            statement_id = response.get('statement_id')
            logger.info(f"[EXECUTE_QUERY] Statement started: {statement_id}")
        except Exception as e:
            logger.error(f"[EXECUTE_QUERY] ❌ Failed to start statement: {str(e)}")
            raise
        
        # Poll for completion
        max_attempts = timeout
        logger.info(f"[EXECUTE_QUERY] Polling for completion (max {max_attempts}s)...")
        for i in range(max_attempts):
            status_response = self._make_api_request('GET', f'/api/2.0/sql/statements/{statement_id}')
            state = status_response.get('status', {}).get('state')
            
            if i % 5 == 0:  # Log every 5 seconds
                logger.info(f"[EXECUTE_QUERY] Poll {i+1}/{max_attempts}: State={state}")
            
            if state == 'SUCCEEDED':
                logger.info(f"[EXECUTE_QUERY] ✅ Query completed successfully")
                result = status_response.get('result', {})
                return {
                    'data_array': result.get('data_array', []),
                    'columns': result.get('schema', {}).get('columns', [])
                }
            elif state in ['FAILED', 'CANCELED']:
                error = status_response.get('status', {}).get('error', {})
                raise Exception(f"Query failed: {error.get('message', 'Unknown error')}")
            
            time.sleep(1)
        
        raise Exception(f"Query timeout after {timeout} seconds")
    
    def _query_overall_score(self, summary_dataset_table: str, warehouse_id: str) -> Dict[str, Any]:
        """Return {'overall_score': float} from dimension averages."""
        result = self._execute_query(
            f"""SELECT ROUND(AVG(dataset_score), 2) AS overall_score
FROM {summary_dataset_table}
WHERE check_type != 'overall'""",
            warehouse_id,
        )
        if result.get('data_array'):
            row = result['data_array'][0]
            return {'overall_score': float(row[0]) if row[0] is not None else 0.0}
        return {}

    def _query_totals(self, summary_columns_table: str, warehouse_id: str) -> Dict[str, Any]:
        """Return {'total_rows': int, 'total_columns': int}."""
        result = self._execute_query(
            f"""SELECT MAX(total_rows)             AS total_rows,
       COUNT(DISTINCT column_name) AS total_columns
FROM {summary_columns_table}""",
            warehouse_id,
        )
        if result.get('data_array'):
            row = result['data_array'][0]
            return {
                'total_rows':    int(row[0]) if row[0] is not None else 0,
                'total_columns': int(row[1]) if row[1] is not None else 0,
            }
        return {}

    def _query_status_distribution(self, summary_columns_table: str, warehouse_id: str) -> Dict[str, Any]:
        """Return {'ok_columns', 'monitor_columns', 'error_columns'} from worst-case column status."""
        result = self._execute_query(
            f"""SELECT SUM(CASE WHEN col_status = 'OK'      THEN 1 ELSE 0 END) AS ok_count,
       SUM(CASE WHEN col_status = 'Warning'  THEN 1 ELSE 0 END) AS warning_count,
       SUM(CASE WHEN col_status = 'KO'    THEN 1 ELSE 0 END) AS error_count
FROM (
    SELECT column_name,
           CASE WHEN SUM(CASE WHEN status = 'KO' THEN 1 ELSE 0 END) > 0 THEN 'KO'
                WHEN SUM(CASE WHEN status = 'Warning' THEN 1 ELSE 0 END) > 0 THEN 'Warning'
                ELSE 'OK' END AS col_status
    FROM {summary_columns_table}
    GROUP BY column_name
) t""",
            warehouse_id,
        )
        if result.get('data_array'):
            row = result['data_array'][0]
            return {
                'ok_columns':      int(row[0]) if row[0] is not None else 0,
                'monitor_columns': int(row[1]) if row[1] is not None else 0,
                'error_columns':   int(row[2]) if row[2] is not None else 0,
            }
        return {}

    def _query_dimension_scores(self, summary_dataset_table: str, warehouse_id: str) -> Dict[str, Any]:
        """Return {'dimension_scores', 'best_dimension', 'weakest_dimension'}."""
        result = self._execute_query(
            f"""SELECT check_type, ROUND(dataset_score, 2) AS avg_score
FROM {summary_dataset_table}
WHERE check_type != 'overall'
ORDER BY dataset_score DESC""",
            warehouse_id,
        )
        dim_scores = [
            (row[0], float(row[1]))
            for row in result.get('data_array', [])
            if row[0] and row[1] is not None
        ]
        metrics: Dict[str, Any] = {'dimension_scores': dim_scores}
        if dim_scores:
            metrics['best_dimension']    = dim_scores[0]
            metrics['weakest_dimension'] = dim_scores[-1]
        return metrics

    def _query_lowest_column(self, summary_columns_table: str, warehouse_id: str) -> Dict[str, Any]:
        """Return {'lowest_column': {...}} for the column with the lowest score."""
        result = self._execute_query(
            f"""SELECT column_name,
       ROUND(MIN(score), 2) AS min_score,
       SUM(invalid_count)   AS total_invalid,
       SUM(null_count)      AS total_null
FROM {summary_columns_table}
GROUP BY column_name
ORDER BY min_score ASC
LIMIT 1""",
            warehouse_id,
        )
        if result.get('data_array'):
            row = result['data_array'][0]
            return {
                'lowest_column': {
                    'name':          row[0],
                    'score':         float(row[1]) if row[1] is not None else 0.0,
                    'invalid_count': int(row[2])   if row[2] is not None else 0,
                    'null_count':    int(row[3])   if row[3] is not None else 0,
                }
            }
        return {}

    def _collect_dashboard_metrics(self, summary_columns_table: str, summary_dataset_table: str,
                                    warehouse_id: str, thresholds: Dict[str, float]) -> Dict[str, Any]:
        """Query DQ result tables and compile all metrics needed for the Quality Summary section"""
        metrics: Dict[str, Any] = {}
        try:
            metrics.update(self._query_overall_score(summary_dataset_table, warehouse_id))
            metrics.update(self._query_totals(summary_columns_table, warehouse_id))
            metrics.update(self._query_status_distribution(summary_columns_table, warehouse_id))
            metrics.update(self._query_dimension_scores(summary_dataset_table, warehouse_id))
            metrics.update(self._query_lowest_column(summary_columns_table, warehouse_id))
        except Exception as e:
            logger.warning(f"[METRICS] Could not collect dashboard metrics: {e}")
        return metrics

    def _generate_left_panel_markdown(self, project_name: str, job_name: str,
                                      metrics: Dict[str, Any],
                                      thresholds: Dict[str, float]) -> str:
        """Generate the Markdown content for the left metadata panel (threshold legend only)"""
        ok_t   = thresholds['ok_threshold']
        warn_t = thresholds['warning_threshold']

        lines = [
            "## Threshold Legend",
            "",
            "| Status | Threshold |",
            "|---|---|",
            f"| 🟢 OK | \u2265 {ok_t}% |",
            f"| 🟡 Monitor | \u2265 {warn_t}% |",
            f"| 🔴 Error | < {warn_t}% |",
        ]
        return "\n".join(lines)

    @staticmethod
    def _resolve_overall_status_line(overall_score: float, ok_t: float,
                                     monitor_columns: int, error_columns: int,
                                     total_columns: int) -> str:
        """Return the global assessment sentence for the quality summary."""
        if overall_score >= ok_t and monitor_columns == 0 and error_columns == 0:
            return "🟢 **Overall assessment:** Data quality is **excellent**. All analyzed columns meet expected thresholds."
        if overall_score >= ok_t and error_columns == 0:
            return "🟢 **Overall assessment:** Data quality is globally **strong**, though some columns should be monitored."
        if error_columns > 0 and error_columns <= total_columns * 0.20:
            return "🟡 **Overall assessment:** Some data quality issues were detected. Targeted remediation may be required."
        return "🔴 **Overall assessment:** Data quality issues are significant and should be addressed before downstream usage."

    def _generate_quality_summary_markdown(self, metrics: Dict[str, Any],
                                            thresholds: Dict[str, float],
                                            project_name: str = '',
                                            job_name: str = '') -> str:
        """Generate the dynamic Quality Summary Markdown for the right panel"""
        overall_score   = metrics.get('overall_score', 0.0)
        ok_columns      = metrics.get('ok_columns', 0)
        monitor_columns = metrics.get('monitor_columns', 0)
        error_columns   = metrics.get('error_columns', 0)
        total_columns   = metrics.get('total_columns', 1) or 1
        ok_t   = thresholds['ok_threshold']
        warn_t = thresholds['warning_threshold']

        status_line = self._resolve_overall_status_line(
            overall_score, ok_t, monitor_columns, error_columns, total_columns
        )

        lines = ["## Quality Summary", "", status_line, ""]

        # Scope
        total_rows = metrics.get('total_rows')
        rows_str   = f"{total_rows:,}" if isinstance(total_rows, int) else "N/A"
        lines += [
            "### Scope analyzed",
            f"- **Rows analyzed:** {rows_str}",
            f"- **Columns analyzed:** {total_columns}",
            "",
        ]

        # Status distribution
        lines += [
            "### Status distribution",
            f"- 🟢 **Healthy columns:** {ok_columns}",
            f"- 🟡 **Columns to monitor:** {monitor_columns}",
            f"- 🔴 **Columns requiring action:** {error_columns}",
            "",
        ]

        # Dimension insights
        dim_scores = metrics.get('dimension_scores', [])
        if dim_scores:
            all_equal = all(abs(s[1] - dim_scores[0][1]) < 0.1 for s in dim_scores)
            if all_equal:
                dim_names = ", ".join(s[0].capitalize() for s in dim_scores)
                lines += [
                    "### Dimension insights",
                    f"- **Strongest dimension(s):** {dim_names}",
                    "- **Weakest dimension(s):** None",
                    "",
                    "All quality dimensions show consistent performance.",
                    "",
                ]
            else:
                best    = metrics.get('best_dimension',    ('N/A', 0.0))
                weakest = metrics.get('weakest_dimension', ('N/A', 0.0))
                lines += [
                    "### Dimension insights",
                    f"- **Strongest dimension:** {best[0].capitalize()} ({best[1]:.1f}%)",
                    f"- **Weakest dimension:** {weakest[0].capitalize()} ({weakest[1]:.1f}%)",
                    "",
                ]
                if weakest[1] < ok_t:
                    lines.append(f"\u26a0\ufe0f **{weakest[0].capitalize()} is currently the weakest dimension.**")
                    lines.append("")

        # Lowest scoring column (only shown when not all columns are at 100%)
        lowest = metrics.get('lowest_column')
        if lowest and lowest['score'] < 100.0:
            lines += [
                "## Column Quality Insight",
                "",
                f"\U0001f50e **Lowest scoring column:** `{lowest['name']}`",
                "",
                f"- Score: **{lowest['score']:.1f}%**",
                f"- Invalid values: **{lowest['invalid_count']}**",
                f"- Null values: **{lowest['null_count']}**",
                "",
            ]

        # Interpretation
        lines += ["### Interpretation", ""]
        if error_columns == 0 and monitor_columns == 0:
            lines.append("All columns meet expected quality thresholds. No remediation is required at this time.")
        elif error_columns == 0:
            lines.append(
                f"No critical issues detected. **{monitor_columns}** column(s) are below the OK threshold "
                f"and should be monitored for potential degradation."
            )
        else:
            lines.append(
                f"**{error_columns}** column(s) fall below acceptable quality thresholds. "
                f"Review invalid and null value distributions to identify root causes and apply targeted remediation."
            )

        return "\n".join(lines)

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """Sanitize names for table references"""
        import re
        return re.sub(r'[^a-zA-Z0-9_]', '_', name).lower()
