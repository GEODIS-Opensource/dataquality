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
UI Components for Loading States

Provides visual feedback while data is being loaded asynchronously
"""

import streamlit as st
from typing import Optional


def show_skeleton_loader(num_cards: int = 3, title: str = "Loading..."):
    """
    Show skeleton loader for project cards
    
    Args:
        num_cards: Number of skeleton cards to show
        title: Title to display above skeleton
    """
    st.markdown(f"### {title}")
    
    for i in range(num_cards):
        st.markdown(f"""
            <div style="
                border: 2px solid #E5E7EB;
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 15px;
                background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
                background-size: 200% 100%;
                animation: shimmer 1.5s infinite;
                height: 120px;
            ">
            </div>
            <style>
                @keyframes shimmer {{
                    0% {{ background-position: 200% 0; }}
                    100% {{ background-position: -200% 0; }}
                }}
            </style>
        """, unsafe_allow_html=True)


def show_loading_indicator(message: str = "Loading data...", icon: str = "⏳"):
    """
    Show a nice loading indicator
    
    Args:
        message: Message to display
        icon: Icon to show
    """
    st.markdown(f"""
        <div style="
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 40px 20px;
            background-color: #F3F4F6;
            border-radius: 10px;
            margin: 20px 0;
        ">
            <div style="text-align: center;">
                <div style="font-size: 3rem; margin-bottom: 10px; animation: pulse 1.5s infinite;">
                    {icon}
                </div>
                <div style="color: #6B7280; font-size: 1.1rem;">
                    {message}
                </div>
            </div>
        </div>
        <style>
            @keyframes pulse {{
                0%, 100% {{ opacity: 1; transform: scale(1); }}
                50% {{ opacity: 0.7; transform: scale(1.1); }}
            }}
        </style>
    """, unsafe_allow_html=True)


def show_instant_page_shell():
    """
    Show the page shell instantly while data loads
    This improves perceived performance
    """
    st.markdown("### 📋 Data Quality Projects")
    st.markdown("Create and manage your data quality analysis projects.")
    st.markdown("---")
    
    # Show placeholder for create form
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("#### 🆕 Create New Project")
        show_loading_indicator("Initializing form...", "📝")
    
    with col2:
        st.markdown("#### 📊 Statistics")
        st.markdown("""
            <div style="
                padding: 15px;
                background-color: #F9FAFB;
                border-radius: 8px;
                text-align: center;
                color: #9CA3AF;
            ">
                Loading statistics...
            </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("#### 📂 Existing Projects")
    show_skeleton_loader(num_cards=3, title="")
