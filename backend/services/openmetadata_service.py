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
OpenMetadata Service
Pushes DQ results from Databricks Delta tables (_summary_columns, _summary_dataset)
into OpenMetadata test cases and test case results.

Adapted from score_status/recipe.py (Dataiku version).
"""
import os
import json
import time
import logging
import requests
from datetime import datetime
from urllib.parse import quote
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

_DIMENSIONS = ("completeness", "validity", "uniqueness", "consistency")


class OpenMetadataService:

    def __init__(self):
        self.omd_base_url = os.getenv("OMD_BASE_URL", "https://openmetadata.intranet.geodis.org/api").rstrip("/")
        self.omd_token = os.getenv("OMD_TOKEN", "")
        # Optional corporate CA bundle for the intranet endpoint; defaults to the system trust store
        self._verify = os.getenv("OMD_CA_BUNDLE", "").strip() or True

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.omd_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Data fetching from Databricks Delta (_summary_columns / _summary_dataset)
    # ------------------------------------------------------------------

    def _fetch_summary_data(self, norm_project: str, norm_job: str) -> Dict[str, Any]:
        """
        Query _summary_columns and _summary_dataset (latest run) via Databricks SQL.
        Returns dict with keys 'columns_rows' and 'dataset_rows'.
        """
        from db_utils import get_db_connection
        catalog = os.getenv("UC_CATALOG", "")
        results_schema = os.getenv("UC_RESULTS_SCHEMA", "db_gdm_dq_results")
        summary_columns_table = f"{catalog}.{results_schema}.dq_{norm_project}_{norm_job}_summary_columns"
        summary_dataset_table = f"{catalog}.{results_schema}.dq_{norm_project}_{norm_job}_summary_dataset"

        columns_rows = []
        dataset_rows = []

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # --- _summary_columns (latest run) ---
                col_query = f"""
                    SELECT column_name, check_type, score, status, faulty_count, total_rows
                    FROM {summary_columns_table}
                    WHERE CAST(execution_timestamp AS TIMESTAMP) = (
                        SELECT MAX(CAST(execution_timestamp AS TIMESTAMP))
                        FROM {summary_columns_table}
                    )
                """
                cursor.execute(col_query)
                col_cols = [d[0] for d in cursor.description]
                for row in cursor.fetchall():
                    columns_rows.append(dict(zip(col_cols, row)))

                # --- _summary_dataset (latest run) ---
                ds_query = f"""
                    SELECT check_type, dataset_score, dataset_status
                    FROM {summary_dataset_table}
                    WHERE CAST(execution_timestamp AS TIMESTAMP) = (
                        SELECT MAX(CAST(execution_timestamp AS TIMESTAMP))
                        FROM {summary_dataset_table}
                    )
                """
                cursor.execute(ds_query)
                ds_cols = [d[0] for d in cursor.description]
                for row in cursor.fetchall():
                    dataset_rows.append(dict(zip(ds_cols, row)))

        logger.info(f"[OMD] Fetched {len(columns_rows)} column rows, {len(dataset_rows)} dataset rows")
        return {"columns_rows": columns_rows, "dataset_rows": dataset_rows}

    # ------------------------------------------------------------------
    # OpenMetadata ÔÇö Test Suite
    # ------------------------------------------------------------------

    def _ensure_test_suite(self, fqn: str):
        """Create or update the executable test suite for the asset."""
        url = f"{self.omd_base_url}/v1/dataQuality/testSuites/executable"
        body = {
            "name": fqn + ".testSuite",
            "executableEntityReference": fqn,
            "basicEntityReference": fqn,
        }
        resp = requests.put(url, headers=self._headers(), json=body, verify=self._verify)
        logger.info(f"[OMD] Test suite PUT {resp.status_code}")

    # ------------------------------------------------------------------
    # OpenMetadata ÔÇö Table-level test case
    # ------------------------------------------------------------------

    def _push_table_test_case(self, fqn: str, dataset_rows: List[Dict]) -> int:
        """
        Create/update table test case and push result.
        Returns 1 on success, 0 on failure.
        """
        table_name = fqn.split(".")[-1]
        test_case_name = table_name + " dq summary"
        entity_link = f"<#E::table::{fqn}>"
        unix_timestamp = int(datetime.now().timestamp() * 1000)

        # --- Create/update test case ---
        case_body = {
            "description": f"Test_Case_{table_name}",
            "displayName": test_case_name,
            "entityLink": entity_link,
            "name": test_case_name,
            "parameterValues": [
                {"name": "minValue", "value": 0},
                {"name": "maxValue", "value": 10000000},
            ],
            "testDefinition": "tableRowCountToBeBetween",
        }
        put_url = f"{self.omd_base_url}/v1/dataQuality/testCases"
        resp = requests.post(put_url, headers=self._headers(), json=case_body, verify=self._verify)
        logger.info(f"[OMD] Table test case POST {resp.status_code}")

        if resp.status_code in (200, 201):
            test_case_fqn = resp.json().get("fullyQualifiedName", f"{fqn}.{test_case_name}")
        elif resp.status_code == 409:
            # Already exists
            test_case_fqn = f"{fqn}.{test_case_name}"
        else:
            logger.error(f"[OMD] Table test case creation failed ({resp.status_code}): {resp.text}")
            return 0

        # --- Compute scores from _summary_dataset ---
        def safe_float(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        scores = {r["check_type"]: safe_float(r["dataset_score"]) for r in dataset_rows}
        valid_scores = [v for v in scores.values() if v is not None]
        average_score = round(sum(valid_scores) / len(valid_scores), 2) if valid_scores else 0.0

        if average_score >= 98:
            test_case_status = "Success"
        elif average_score >= 95:
            test_case_status = "Aborted"
        else:
            test_case_status = "Failed"

        test_result_value = []
        for dim in ("completeness", "validity", "uniqueness", "consistency"):
            if scores.get(dim) is not None:
                test_result_value.append({"name": dim.capitalize(), "value": scores[dim]})

        result_body = {
            "testCaseStatus": test_case_status,
            "testResultValue": test_result_value,
            "timestamp": unix_timestamp,
        }
        encoded_fqn = quote(test_case_fqn, safe="")
        result_url = f"{self.omd_base_url}/v1/dataQuality/testCases/testCaseResults/{encoded_fqn}"
        result_resp = requests.put(result_url, headers=self._headers(), json=result_body, verify=self._verify)
        logger.info(f"[OMD] Table test case result PUT {result_resp.status_code}")
        return 1 if result_resp.status_code in (200, 201) else 0

    # ------------------------------------------------------------------
    # OpenMetadata ÔÇö Column-level test cases
    # ------------------------------------------------------------------

    def _get_omd_table_columns(self, fqn: str) -> set:
        """Fetch column names registered in OMD for this asset."""
        url = f"{self.omd_base_url}/v1/tables/name/{fqn}"
        resp = requests.get(url, headers=self._headers(), verify=self._verify)
        if resp.status_code != 200:
            logger.warning(f"[OMD] Could not fetch table metadata for {fqn}: {resp.status_code}")
            return set()
        return {c["name"] for c in resp.json().get("columns", [])}

    def _push_column_test_cases(self, fqn: str, columns_rows: List[Dict]) -> int:
        """
        For each column in _summary_columns, create/update test case and push result.
        Returns number of columns successfully pushed.
        """
        omd_columns = self._get_omd_table_columns(fqn)
        unix_timestamp = int(datetime.now().timestamp() * 1000)

        by_column = self._group_rows_by_column(columns_rows)

        pushed = 0
        for col, data in by_column.items():
            if omd_columns and col not in omd_columns:
                logger.info(f"[OMD] Skipping column '{col}' ÔÇö not in OMD table")
                continue

            if self._push_column_test_case(fqn, col, data, unix_timestamp):
                pushed += 1

        return pushed

    @staticmethod
    def _group_rows_by_column(columns_rows: List[Dict]) -> Dict[str, Dict[str, Any]]:
        """Group _summary_columns rows by column name (scores, statuses, faulty counts per check type)."""
        by_column: Dict[str, Dict[str, Any]] = {}
        for row in columns_rows:
            entry = by_column.setdefault(
                row["column_name"], {"scores": {}, "statuses": {}, "faulty": {}, "overall_status": None}
            )
            check_type = row["check_type"]
            if check_type == "overall":
                entry["overall_status"] = row.get("status")
            else:
                entry["scores"][check_type] = row.get("score")
                entry["statuses"][check_type] = row.get("status")
                entry["faulty"][check_type] = row.get("faulty_count")
        return by_column

    @staticmethod
    def _faulty_description(faulty: Dict[str, Any]) -> str:
        return ", ".join(
            f"{dim.capitalize()}Faulty: {int(faulty[dim])}"
            for dim in _DIMENSIONS
            if faulty.get(dim) is not None
        )

    @staticmethod
    def _score_result_values(scores: Dict[str, Any]) -> List[Dict[str, Any]]:
        values = []
        for dim in _DIMENSIONS:
            try:
                if scores.get(dim) is not None:
                    values.append({"name": dim.capitalize(), "value": float(scores[dim])})
            except (TypeError, ValueError):
                pass
        return values

    def _upsert_column_test_case(self, col: str, entity_link: str, description: str) -> None:
        case_body = {
            "description": description,
            "displayName": col,
            "entityLink": entity_link,
            "name": col,
            "parameterValues": [
                {"name": "minLength", "value": 80},
                {"name": "maxLength", "value": 100},
            ],
            "testDefinition": "columnValueLengthsToBeBetween",
        }
        put_resp = requests.put(
            f"{self.omd_base_url}/v1/dataQuality/testCases",
            headers=self._headers(),
            json=case_body,
            verify=self._verify,
        )
        logger.info(f"[OMD] Column '{col}' test case PUT {put_resp.status_code}")

    def _find_test_case(self, entity_link: str):
        """Return (id, fullyQualifiedName) of the test case attached to the entity link, or (None, None)."""
        search_resp = requests.get(
            f"{self.omd_base_url}/v1/dataQuality/testCases",
            headers=self._headers(),
            params={"entityLink": entity_link},
            verify=self._verify,
        )
        if search_resp.status_code != 200:
            return None, None
        tc_data = search_resp.json().get("data", [])
        if not tc_data:
            return None, None
        return tc_data[0]["id"], tc_data[0].get("fullyQualifiedName")

    def _patch_test_case_description(self, test_case_id: str, test_case_fqn: str, description: str) -> str:
        """Replace the test case description with the faulty counts; returns the (possibly updated) FQN."""
        patch_headers = self._headers()
        patch_headers["Content-Type"] = "application/json-patch+json"
        patch_body = [{"op": "replace", "path": "/description", "value": description}]
        patch_resp = requests.patch(
            f"{self.omd_base_url}/v1/dataQuality/testCases/{test_case_id}",
            headers=patch_headers,
            data=json.dumps(patch_body),
            verify=self._verify,
        )
        time.sleep(0.3)
        if patch_resp.status_code == 200:
            return patch_resp.json().get("fullyQualifiedName", test_case_fqn)
        return test_case_fqn

    def _push_column_test_case(self, fqn: str, col: str, data: Dict[str, Any], unix_timestamp: int) -> bool:
        """Create/update the test case of one column and push its result. Returns True on success."""
        entity_link = f"<#E::table::{fqn}::columns::{col}>"
        description_faulty = self._faulty_description(data["faulty"])

        self._upsert_column_test_case(col, entity_link, description_faulty)

        test_case_id, test_case_fqn = self._find_test_case(entity_link)
        if not test_case_fqn:
            logger.warning(f"[OMD] No test case FQN found for column '{col}', skipping result push")
            return False

        if test_case_id and description_faulty:
            test_case_fqn = self._patch_test_case_description(test_case_id, test_case_fqn, description_faulty)

        overall_status = data.get("overall_status") or "KO"
        result_body = {
            "testCaseStatus": "Success" if overall_status == "OK" else "Failed",
            "testResultValue": self._score_result_values(data["scores"]),
            "timestamp": unix_timestamp,
            "fqn": test_case_fqn,
        }
        encoded_fqn = quote(test_case_fqn, safe="")
        result_url = f"{self.omd_base_url}/v1/dataQuality/testCases/testCaseResults/{encoded_fqn}"
        result_resp = requests.post(result_url, headers=self._headers(), json=result_body, verify=self._verify)
        logger.info(f"[OMD] Column '{col}' result POST {result_resp.status_code}")

        if result_resp.status_code in (200, 201):
            return True
        logger.warning(f"[OMD] Column '{col}' result failed: {result_resp.text}")
        return False

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def publish(self, norm_project: str, norm_job: str, fqn: str) -> Dict[str, Any]:
        """
        Full publish flow:
          1. Fetch data from Delta tables
          2. Create/update test suite
          3. Push table-level test case + result
          4. Push per-column test cases + results

        Args:
            norm_project: Normalized project name (same convention as table naming)
            norm_job:     Normalized job name
            fqn:          OpenMetadata FullyQualifiedName of the asset

        Returns:
            status dict
        """
        logger.info(f"[OMD] Token present: {bool(self.omd_token)}, length: {len(self.omd_token)}")

        if not self.omd_token:
            return {"status": "error", "message": "OMD_TOKEN environment variable not set"}

        logger.info(f"[OMD] Starting publish for {fqn} (project={norm_project}, job={norm_job})")

        try:
            summary = self._fetch_summary_data(norm_project, norm_job)
        except Exception as e:
            logger.error(f"[OMD] Failed to fetch summary data: {e}")
            return {"status": "error", "message": f"Failed to read DQ results: {str(e)}"}

        columns_rows = summary["columns_rows"]
        dataset_rows = summary["dataset_rows"]

        if not columns_rows:
            return {"status": "error", "message": "No DQ results found. Run the job first."}

        # 1. Test suite
        try:
            self._ensure_test_suite(fqn)
        except Exception as e:
            logger.warning(f"[OMD] Test suite creation failed (non-blocking): {e}")

        # 2. Table-level test case
        table_ok = 0
        try:
            table_ok = self._push_table_test_case(fqn, dataset_rows)
        except Exception as e:
            logger.warning(f"[OMD] Table test case failed (non-blocking): {e}")

        # 3. Column-level test cases
        columns_pushed = 0
        try:
            columns_pushed = self._push_column_test_cases(fqn, columns_rows)
        except Exception as e:
            logger.error(f"[OMD] Column test cases failed: {e}")
            return {"status": "error", "message": f"Column push failed: {str(e)}"}

        logger.info(f"[OMD] Publish complete ÔÇö table_ok={table_ok}, columns_pushed={columns_pushed}")
        return {
            "status": "success",
            "message": f"Published to OpenMetadata: {columns_pushed} column(s) updated.",
            "table_pushed": bool(table_ok),
            "columns_pushed": columns_pushed,
            "fqn": fqn,
        }
