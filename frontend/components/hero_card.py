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
import streamlit.components.v1 as components

def render_hero_card(title, description, cta_text="Open Data Quality Tool", cta_page="pages/Tool.py"):
    """Render hero card with integrated clickable area"""
    
    # Render the card with onclick handler
    st.markdown(f"""
        <div class="hero-card-wrapper" id="hero-card-clickable" style="cursor: pointer;">
            <div class="hero-card">
                <div class="hero-title">{title}</div>
                <div class="hero-description">{description}</div>
                <div class="hero-cta-text">
                    {cta_text} →
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    # (Button for navigation removed)
    
    # JavaScript to trigger button click when card is clicked
    components.html("""
        <script>
        const heroCard = window.parent.document.getElementById('hero-card-clickable');
        if (heroCard) {
            heroCard.addEventListener('click', function() {
                const buttons = window.parent.document.querySelectorAll('button[kind="primary"]');
                buttons.forEach(btn => {
                    if (btn.textContent.includes('Navigate to Tool')) {
                        btn.click();
                    }
                });
            });
        }
        </script>
    """, height=0)
