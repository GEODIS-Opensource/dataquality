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

import streamlit as st
from datetime import datetime

def render_activity_item(activity_type, dataset_name, status, timestamp):
    """Render a single activity item"""
    status_colors = {
        "Success": "#10B981",
        "Failed": "#EF4444",
        "Critical": "#DC2626",
        "Warning": "#F59E0B"
    }
    
    color = status_colors.get(status, "#64748B")
    
    st.markdown(f"""
        <div class="activity-item" style="border-left-color: {color};">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <strong>{activity_type}</strong> — {dataset_name} — 
                    <span style="color: {color}; font-weight: 600;">{status}</span>
                </div>
                <div class="activity-timestamp">{timestamp}</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

def render_activity_list(activities=None, title="Latest Activity", max_items=5):
    """Render activity list section"""
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
    
    if not activities or len(activities) == 0:
        st.info("No recent activity")
        return
    
    # Display only the latest max_items activities
    for activity in activities[:max_items]:
        render_activity_item(
            activity.get("type", "Activity"),
            activity.get("dataset", "Unknown"),
            activity.get("status", "Completed"),
            activity.get("timestamp", "—")
        )

# Sample activity data for testing
SAMPLE_ACTIVITIES = [
    {
        "type": "Run completed",
        "dataset": "Customer_Master",
        "status": "Success",
        "timestamp": "12:04"
    },
    {
        "type": "Threshold updated",
        "dataset": "Orders",
        "status": "Success",
        "timestamp": "09:18"
    },
    {
        "type": "Issue detected",
        "dataset": "Finance_Transactions",
        "status": "Critical",
        "timestamp": "08:51"
    }
]
