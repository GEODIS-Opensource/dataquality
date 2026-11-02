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

def render_kpi_cards(kpis):
    """Render KPI cards in a horizontal row"""
    cols = st.columns(len(kpis))
    
    for idx, kpi in enumerate(kpis):
        with cols[idx]:
            st.markdown(f"""
                <div class="kpi-card">
                    <div class="kpi-value">{kpi['value']}</div>
                    <div class="kpi-label">{kpi['label']}</div>
                    <div class="kpi-subtext">{kpi.get('subtext', '')}</div>
                </div>
            """, unsafe_allow_html=True)

def render_kpi_section(kpis, title="At a glance"):
    """Render complete KPI section with title and cards"""
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
    render_kpi_cards(kpis)
