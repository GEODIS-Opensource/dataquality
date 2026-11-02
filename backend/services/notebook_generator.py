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
Notebook Generator Service
Generates PySpark notebook code dynamically based on configuration
"""
import json
from typing import Dict, Any, List
import os


class NotebookGenerator:
    """Generates PySpark notebooks for data quality jobs"""
    
    def __init__(self):
        self.templates_dir = os.path.join(os.path.dirname(__file__), '..', 'notebooks')
    
    def _load_template(self, template_name: str) -> str:
        """Load notebook template from file"""
        template_path = os.path.join(self.templates_dir, f"{template_name}.py")
        with open(template_path, 'r') as f:
            return f.read()
    
    def _inject_config(self, template: str, config: Dict[str, Any]) -> str:
        """Inject configuration values into template placeholders"""
        notebook_code = template
        
        for key, value in config.items():
            placeholder = f"{{{{{key}}}}}"
            
            # Handle different value types
            if isinstance(value, (list, dict)):
                # Convert to JSON for lists and dicts
                value_str = json.dumps(value)
            elif isinstance(value, str):
                # Wrap strings in quotes
                value_str = f'"{value}"'
            else:
                # Numbers, booleans, etc.
                value_str = str(value)
            
            notebook_code = notebook_code.replace(placeholder, value_str)
        
        return notebook_code
    
    def generate_prepare_input_notebook(self, project_id: int, catalog: str, schema: str,
                                       source_type: str, source_path: str) -> str:
        """Generate prepare input notebook"""
        template = self._load_template("prepare_input")
        
        config = {
            "PROJECT_ID": project_id,
            "CATALOG": catalog,
            "SCHEMA": schema,
            "SOURCE_TYPE": source_type,
            "SOURCE_PATH": source_path
        }
        
        return self._inject_config(template, config)
    
    def generate_completeness_check_notebook(self, project_id: int, catalog: str, schema: str,
                                            columns: List[str], extra_empty_values: List[str] = None) -> str:
        """Generate completeness check notebook"""
        template = self._load_template("completeness_check")
        
        config = {
            "PROJECT_ID": project_id,
            "CATALOG": catalog,
            "SCHEMA": schema,
            "COLUMNS_TO_CHECK": columns,
            "EXTRA_EMPTY_VALUES": extra_empty_values or []
        }
        
        return self._inject_config(template, config)
    
    def generate_aggregate_checks_notebook(self, project_id: int, catalog: str, schema: str,
                                          enabled_dimensions: List[str], columns: List[str]) -> str:
        """Generate aggregate checks notebook"""
        template = self._load_template("aggregate_checks")
        
        config = {
            "PROJECT_ID": project_id,
            "CATALOG": catalog,
            "SCHEMA": schema,
            "ENABLED_DIMENSIONS": enabled_dimensions,
            "COLUMNS_TO_CHECK": columns
        }
        
        return self._inject_config(template, config)
    
    def generate_column_summary_notebook(self, project_id: int, catalog: str, schema: str,
                                        columns: List[str], enabled_dimensions: List[str],
                                        threshold_ok: float = 100.0, threshold_warning: float = 98.0) -> str:
        """Generate column summary notebook"""
        template = self._load_template("generate_column_summary")
        
        config = {
            "PROJECT_ID": project_id,
            "CATALOG": catalog,
            "SCHEMA": schema,
            "COLUMNS_TO_CHECK": columns,
            "ENABLED_DIMENSIONS": enabled_dimensions,
            "THRESHOLD_OK": threshold_ok,
            "THRESHOLD_WARNING": threshold_warning
        }
        
        return self._inject_config(template, config)
    
    def generate_dataset_summary_notebook(self, project_id: int, catalog: str, schema: str,
                                         enabled_dimensions: List[str],
                                         threshold_ok: float = 100.0, threshold_warning: float = 98.0) -> str:
        """Generate dataset summary notebook"""
        template = self._load_template("generate_dataset_summary")
        
        config = {
            "PROJECT_ID": project_id,
            "CATALOG": catalog,
            "SCHEMA": schema,
            "ENABLED_DIMENSIONS": enabled_dimensions,
            "THRESHOLD_OK": threshold_ok,
            "THRESHOLD_WARNING": threshold_warning
        }
        
        return self._inject_config(template, config)
    
    def generate_faulty_records_notebook(self, project_id: int, catalog: str, schema: str) -> str:
        """Generate faulty records extraction notebook"""
        template = self._load_template("extract_faulty_records")
        
        config = {
            "PROJECT_ID": project_id,
            "CATALOG": catalog,
            "SCHEMA": schema
        }
        
        return self._inject_config(template, config)
