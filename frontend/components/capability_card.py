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

def render_workflow_step(number, title, description):
    """Render a single workflow step card"""
    st.markdown(f"""
        <div class="workflow-step">
            <div class="step-number">{number}</div>
            <div class="step-title">{title}</div>
            <div class="step-description">{description}</div>
        </div>
    """, unsafe_allow_html=True)

def render_workflow_section(steps, title="How it works"):
    """Render complete workflow section with title and step cards in vertical timeline"""
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
    
    # Render vertical timeline
    st.markdown('<div class="timeline-container">', unsafe_allow_html=True)
    
    for idx, step in enumerate(steps):
        # Add connector line before each step except the first
        if idx > 0:
            st.markdown('<div class="timeline-connector"></div>', unsafe_allow_html=True)
        
        render_workflow_step(
            step["number"],
            step["title"],
            step["description"]
        )
    
    st.markdown('</div>', unsafe_allow_html=True)

# Legacy function name for backwards compatibility
def render_capabilities_section(capabilities, title="This application enables"):
    """Legacy function - redirects to workflow section"""
    render_workflow_section(capabilities, title)

def render_capability_card(icon, title, description):
    """Legacy function for backwards compatibility"""
    st.markdown(f"""
        <div class="workflow-step">
            <span class="capability-icon">{icon}</span>
            <div class="step-title">{title}</div>
            <div class="step-description">{description}</div>
        </div>
    """, unsafe_allow_html=True)
