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

"""Component Card UI"""

import streamlit as st


def render_component_card(component, is_selected):
    """Render a component selection card (card visual only, no buttons)
    
    Args:
        component (dict): Component configuration
        is_selected (bool): Whether the component is currently selected
    """
    # Card styling — adaptive for light/dark mode
    border_color = component['color'] if is_selected else "rgba(128,128,128,0.3)"
    bg_color = f"{component['color']}20" if is_selected else "var(--secondary-background-color)"

    st.markdown(f"""
        <div style="
            border: 2px solid {border_color};
            border-radius: 8px;
            padding: 8px 12px;
            background-color: {bg_color};
            margin-bottom: 10px;
            height: 90px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        ">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                <span style="font-size: 1.4rem;">{component['icon']}</span>
                <span style="font-weight: bold; font-size: 1rem; color: var(--text-color);">
                    {component['name']}
                </span>
            </div>
            <div style="font-size: 0.78rem; color: var(--text-color); opacity: 0.65; line-height: 1.3;
                        overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;">
                {component['description']}
            </div>
        </div>
    """, unsafe_allow_html=True)
