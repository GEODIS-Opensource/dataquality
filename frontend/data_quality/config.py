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
Data Quality Configuration

Defines all available data quality components based on recipe templates.
Each component has parameters, category, and visual properties.
"""

import streamlit as st

_EXACT_MATCH = "Exact Match"

# Data Quality Components Configuration
DQ_COMPONENTS = [
    {
        "id": "completeness",
        "name": "Completeness Check",
        "icon": "📋",
        "color": "#3B82F6",
        "description": "Checks for missing values (null, empty strings, whitespace) in key columns",
        "category": "Completeness",
        "params": [
            {
                "name": "key_columns",
                "label": "Key Columns to Check",
                "type": "multiselect",
                "description": "Select columns to check for completeness"
            },
            {
                "name": "null_values",
                "label": "Consider as Null",
                "type": "text",
                "description": "Comma-separated list of values to treat as null (e.g., NA, N/A, NULL)",
                "default": "NA,N/A,NULL"
            }
        ]
    },
    {
        "id": "uniqueness",
        "name": "Uniqueness Check",
        "icon": "🔑",
        "color": "#8B5CF6",
        "description": "Validates that key columns contain unique values with no duplicates",
        "category": "Uniqueness",
        "params": [
            {
                "name": "key_columns",
                "label": "Key Columns",
                "type": "multiselect",
                "description": "Select columns that should contain unique values"
            },
            {
                "name": "check_mode",
                "label": "Check Mode",
                "type": "radio",
                "options": [_EXACT_MATCH, "Fuzzy Match"],
                "default": _EXACT_MATCH,
                "description": "Choose exact matching or fuzzy matching for duplicates"
            },
            {
                "name": "fuzzy_sensitivity",
                "label": "Fuzzy Sensitivity (%)",
                "type": "slider",
                "min": 0,
                "max": 100,
                "default": 80,
                "description": "Similarity threshold for fuzzy matching (0-100%)",
                "show_if": {"check_mode": "Fuzzy Match"}
            }
        ]
    },
    {
        "id": "validity_numeric",
        "name": "Numeric Values Comparison",
        "icon": "🔢",
        "color": "#F59E0B",
        "description": "Compares numeric values from two columns using operators (>, <, =, >=, <=)",
        "category": "Accuracy",
        "params": [
            {
                "name": "column_1",
                "label": "First Column",
                "type": "select",
                "description": "Select first numeric column"
            },
            {
                "name": "operator",
                "label": "Comparison Operator",
                "type": "select",
                "options": ["<", "<=", "=", ">=", ">"],
                "default": ">"
            },
            {
                "name": "column_2",
                "label": "Second Column",
                "type": "select",
                "description": "Select second numeric column"
            }
        ]
    },
    {
        "id": "validity_date",
        "name": "Date Values Comparison",
        "icon": "📅",
        "color": "#F59E0B",
        "description": "Compares date values from two columns using operators (>, <, =, >=, <=)",
        "category": "Accuracy",
        "params": [
            {
                "name": "date_column_1",
                "label": "First Date Column",
                "type": "select",
                "description": "Select first date column"
            },
            {
                "name": "operator",
                "label": "Comparison Operator",
                "type": "select",
                "options": ["<", "<=", "=", ">=", ">"],
                "default": ">"
            },
            {
                "name": "date_column_2",
                "label": "Second Date Column",
                "type": "select",
                "description": "Select second date column"
            }
        ]
    },
    {
        "id": "accuracy_custom_rules",
        "name": "Custom Rules",
        "icon": "🧠",
        "color": "#EF4444",
        "description": "Define custom if/then rules for line-level accuracy checks. Each rule returns 1 when true and 0 when false.",
        "category": "Accuracy",
        "params": [
            {
                "name": "custom_rules",
                "label": "Custom Rules Builder",
                "type": "custom_rules_builder",
                "description": "Add one or more custom rules to evaluate your data with business-specific if statements"
            }
        ]
    },
    {
        "id": "meaning_validity",
        "name": "Validity",
        "icon": "🎯",
        "color": "#10B981",
        "description": "Validates that column values match expected data types (SIREN, SIRET, VAT, email, etc.)",
        "category": "Validity",
        "params": [
            {
                "name": "column_types",
                "label": "Column Type Mapping",
                "type": "column_type_mapping",
                "description": "Map each column to its expected data type"
            }
        ]
    },
    {
        "id": "consistency",
        "name": "Consistency Check",
        "icon": "🔄",
        "color": "#EC4899",
        "description": "Validates consistency between two columns by comparing master column A with validation column B",
        "category": "Consistency",
        "params": [
            {
                "name": "column_a",
                "label": "Master Column (A)",
                "type": "select",
                "description": "Select the master column for comparison"
            },
            {
                "name": "column_b",
                "label": "Validation Column (B)",
                "type": "select",
                "description": "Select the validation column to compare against master"
            },
            {
                "name": "key_columns",
                "label": "Key Columns (Optional)",
                "type": "multiselect",
                "description": "Select key columns for grouping (optional, for future enhancements)"
            },
            {
                "name": "check_mode",
                "label": "Check Mode",
                "type": "radio",
                "options": [_EXACT_MATCH, "Case Insensitive"],
                "default": _EXACT_MATCH,
                "description": "Choose exact matching or case-insensitive comparison"
            }
        ]
    }
]


@st.cache_data
def get_component_by_id(component_id):
    """Get component configuration by ID (cached for performance)"""
    for component in DQ_COMPONENTS:
        if component['id'] == component_id:
            return component
    return None


@st.cache_data
def get_all_categories():
    """Get all unique categories from components (cached for performance)"""
    categories = []
    for component in DQ_COMPONENTS:
        if component['category'] not in categories:
            categories.append(component['category'])
    return categories
