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
st.set_page_config(page_title="Redirecting...", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")

# Hide sidebar and header during redirect
st.markdown("""
    <style>
        [data-testid='stSidebar'], [data-testid='stHeader'], [data-testid='stToolbar'] {display: none;}
        .block-container {padding-top: 2rem;}
    </style>
""", unsafe_allow_html=True)
st.switch_page("pages/Tool.py")

