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

"""Payload Generator for Data Quality API"""

import json
from datetime import datetime


def generate_dq_payload():
    """Generate API payload from current data quality configuration
    
    Returns:
        dict: Complete payload ready for API request
    """
    import streamlit as st
    
    payload = {
        "metadata": {
            "project_id": st.session_state.get('dq_current_project_id') or st.session_state.get('current_project_id'),
            "project_name": _get_current_project_name(),
            "generated_at": datetime.now().isoformat(),
            "version": "1.0"
        },
        "data_source": _generate_data_source_config(),
        "quality_controls": _generate_quality_controls_config(),
        "deployment": _generate_deployment_config(),
        "execution": _generate_execution_config()
    }
    
    return payload


def _get_current_project_name():
    """Get current project name"""
    import streamlit as st
    from .projects import get_current_project
    
    project = get_current_project()
    return project['name'] if project else st.session_state.get('dq_dataset_name', 'Unnamed Project')


def _generate_data_source_config():
    """Generate data source configuration"""
    import streamlit as st
    
    source_type = st.session_state.get('dq_source_type')
    
    if source_type == 'csv':
        return {
            "type": "csv",
            "dataset_name": st.session_state.get('dq_dataset_name'),
            "file_config": {
                "separator": st.session_state.get('dq_csv_separator', ','),
                "quote_char": st.session_state.get('dq_csv_quote_char', '"'),
                "skip_lines": st.session_state.get('dq_csv_skip_lines', 0),
                "has_header": st.session_state.get('dq_csv_has_header', True)
            }
        }
    elif source_type == 'unity_catalog':
        return {
            "type": "unity_catalog",
            "connection": {
                "catalog": st.session_state.get('dq_unity_catalog'),
                "schema": st.session_state.get('dq_unity_schema'),
                "table": st.session_state.get('dq_unity_table')
            }
        }
    else:
        return {
            "type": "unknown",
            "dataset_name": st.session_state.get('dq_dataset_name')
        }


def _generate_quality_controls_config():
    """Generate quality controls configuration"""
    import streamlit as st
    from .config import get_component_by_id
    
    controls = []
    
    selected_components = st.session_state.get('dq_selected_components', [])
    component_configs = st.session_state.get('dq_component_configs', {})
    thresholds = st.session_state.get('dq_thresholds', {})
    component_enabled = st.session_state.get('dq_component_enabled', {})
    
    for component_id in selected_components:
        # Skip if disabled
        if not component_enabled.get(component_id, True):
            continue
        
        component = get_component_by_id(component_id)
        if not component:
            continue
        
        config = component_configs.get(component_id, {})
        component_thresholds = thresholds.get(component_id, {})
        
        control = {
            "component_id": component_id,
            "component_name": component['name'],
            "category": component['category'],
            "enabled": True,
            "parameters": config,
            "thresholds": {}
        }
        
        # Add thresholds for each controlled column
        for column, threshold_config in component_thresholds.items():
            control["thresholds"][column] = {
                "warning": threshold_config.get('warning', 80),
                "ok": threshold_config.get('ok', 95)
            }
        
        controls.append(control)
    
    return {
        "total_controls": len(controls),
        "controls": controls
    }


def _generate_deployment_config():
    """Generate deployment configuration"""
    import streamlit as st
    
    return {
        "job_name": st.session_state.get('dq_job_name', f"dq_job_{st.session_state.get('dq_dataset_name')}"),
        "job_description": st.session_state.get('dq_job_description', ''),
        "notification_email": st.session_state.get('dq_notification_email', ''),
        "failure_action": st.session_state.get('dq_failure_action', 'Alert Only'),
        "retry_attempts": st.session_state.get('dq_retry_attempts', 0),
        "priority": st.session_state.get('dq_priority', 'Medium')
    }


def _generate_execution_config():
    """Generate execution configuration"""
    import streamlit as st
    
    execution_mode = st.session_state.get('dq_execution_mode', 'Run Now')
    
    config = {
        "mode": "immediate" if execution_mode == "▶️ Run Now" else "scheduled"
    }
    
    if execution_mode != "▶️ Run Now":
        config["schedule"] = {
            "type": st.session_state.get('dq_schedule_type', 'Daily'),
            "timezone": st.session_state.get('dq_timezone', 'UTC'),
            "start_date": st.session_state.get('dq_start_date', datetime.now().isoformat()),
            "end_date": st.session_state.get('dq_end_date')
        }
        
        # Add schedule-specific config
        schedule_type = st.session_state.get('dq_schedule_type', 'Daily')
        if schedule_type == 'Daily':
            config["schedule"]["execution_time"] = st.session_state.get('dq_execution_time')
        elif schedule_type == 'Weekly':
            config["schedule"]["day_of_week"] = st.session_state.get('dq_execution_day')
            config["schedule"]["execution_time"] = st.session_state.get('dq_execution_time')
        elif schedule_type == 'Monthly':
            config["schedule"]["day_of_month"] = st.session_state.get('dq_execution_day')
            config["schedule"]["execution_time"] = st.session_state.get('dq_execution_time')
        elif schedule_type == 'Custom (Cron)':
            config["schedule"]["cron_expression"] = st.session_state.get('dq_cron_expression')
    
    return config


def format_payload_json(payload):
    """Format payload as pretty JSON string
    
    Args:
        payload (dict): Payload dictionary
    
    Returns:
        str: Formatted JSON string
    """
    return json.dumps(payload, indent=2, default=str)


def validate_payload(payload):
    """Validate payload completeness
    
    Args:
        payload (dict): Payload to validate
    
    Returns:
        tuple: (is_valid, error_messages)
    """
    errors = []
    
    # Check data source
    if not payload.get('data_source', {}).get('type'):
        errors.append("Data source type is missing")
    
    # Check quality controls
    controls = payload.get('quality_controls', {}).get('controls', [])
    if not controls:
        errors.append("No quality controls enabled")
    
    # Check deployment config
    deployment = payload.get('deployment', {})
    if not deployment.get('job_name'):
        errors.append("Job name is missing")
    
    return (len(errors) == 0, errors)
