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

"""Utility to extract controlled columns from component configurations"""


def extract_controlled_columns(config):
    """Extract controlled columns from a component configuration
    
    Args:
        config (dict): Component configuration
    
    Returns:
        list: List of column names controlled by this component
    """
    controlled_columns = []
    
    # Check for consistency check first (has both column_a/column_b AND key_columns)
    if 'column_a' in config and 'column_b' in config:
        # Consistency check: both master (A) and validation (B) columns
        controlled_columns = [config.get('column_a', ''), config.get('column_b', '')]
    elif 'key_columns' in config:
        controlled_columns = config['key_columns']
    elif 'column_types' in config:
        controlled_columns = list(config['column_types'].keys())
    elif 'column_1' in config:
        controlled_columns = [config.get('column_1', '')]
    elif 'date_column_1' in config:
        controlled_columns = [config.get('date_column_1', '')]
    elif 'custom_rules' in config:
        for rule in config.get('custom_rules', []):
            controlled_columns.extend(rule.get('columns', []))
    
    # Filter out empty strings and duplicates
    return list(set([col for col in controlled_columns if col]))
