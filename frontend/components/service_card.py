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

def render_service_cards(services, cols_per_row=3):
    """Render service cards in a grid layout with links to separate pages"""
    for i in range(0, len(services), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, col in enumerate(cols):
            if i + j < len(services):
                service = services[i + j]
                with col:
                    # Create a link button that navigates to the service page
                    page_path = service['id'].replace('_', '-')
                    st.markdown(f"""
                        <a href="/{page_path}" target="_self" style="text-decoration: none;">
                            <button style="
                                width: 100%;
                                padding: 40px 20px;
                                font-size: 1.1rem;
                                border: 2px solid #E2E8F0;
                                border-radius: 8px;
                                background-color: white;
                                cursor: pointer;
                                transition: all 0.3s ease;
                                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                            " onmouseover="this.style.borderColor='#3B82F6'; this.style.boxShadow='0 4px 12px rgba(59,130,246,0.3)';" 
                               onmouseout="this.style.borderColor='#E2E8F0'; this.style.boxShadow='0 1px 3px rgba(0,0,0,0.1)';">
                                <div style="font-size: 3rem; margin-bottom: 10px;">{service['icon']}</div>
                                <div style="font-weight: 600; color: #1E293B;">{service['title']}</div>
                            </button>
                        </a>
                    """, unsafe_allow_html=True)
                    st.caption(service['description'])
