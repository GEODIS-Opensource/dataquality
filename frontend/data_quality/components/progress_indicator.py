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

"""Progress Indicator Component"""

import streamlit as st


def _is_step_completed(step_num):
    """Check if a step has been completed
    
    Args:
        step_num (int): Step number to check (1-4)
        
    Returns:
        bool: True if step is completed, False otherwise
    """
    if step_num == 1:
        # Step 1 complete: Data source configured
        return (
            st.session_state.get('dq_dataset_preview') is not None or
            st.session_state.get('dq_source_config') is not None
        )
    elif step_num == 2:
        # Step 2 complete: Quality controls selected and configured
        selected_components = st.session_state.get('dq_selected_components', [])
        component_configs = st.session_state.get('dq_component_configs', {})
        return len(selected_components) > 0 and len(component_configs) > 0
    elif step_num == 3:
        # Step 3 complete: Job deployed (has databricks job ID)
        return st.session_state.get('dq_deployed_job_id') is not None
    elif step_num == 4:
        # Step 4 is always accessible once reached
        return True
    return False


def _can_navigate_to_step(target_step, current_step):
    """Check if user can navigate to a target step
    
    Args:
        target_step (int): Step user wants to navigate to
        current_step (int): Current step
        
    Returns:
        bool: True if navigation is allowed, False otherwise
    """
    # Always allow backward navigation
    if target_step < current_step:
        return True
    
    # If we've reached step 4, all steps are unlocked
    max_reached_step = st.session_state.get('dq_max_step_reached', 1)
    if max_reached_step >= 4:
        return True
    
    # For forward navigation, check if previous steps are complete
    if target_step == 2:
        return _is_step_completed(1)
    elif target_step == 3:
        return _is_step_completed(1) and _is_step_completed(2)
    elif target_step == 4:
        return _is_step_completed(1) and _is_step_completed(2) and _is_step_completed(3)
    
    return False


def _navigate_and_save(target_step: int) -> None:
    """Navigate to a step and trigger auto-save (used as st.button on_click callback)."""
    st.session_state.dq_step = target_step
    from ..projects import save_project_state
    save_project_state()


def _resolve_step_appearance(step_num: int, current_step: int) -> tuple:
    """Return (status_icon, status_text, is_clickable, button_type) for a step."""
    can_navigate = _can_navigate_to_step(step_num, current_step)
    if step_num == current_step:
        return "🔵", f"**{step_num}. {{step}}**", False, "primary"
    if step_num < current_step:
        icon = "✅" if _is_step_completed(step_num) else "⚠️"
        return icon, f"**{step_num}. {{step}}**", can_navigate, "secondary"
    # future step
    icon = "⚪" if can_navigate else "🔒"
    return icon, f"{step_num}. {{step}}", can_navigate, "secondary"


def _render_step_indicator(step_num: int, step: str, current_step: int) -> None:
    """Render one step as a clickable button, locked div, or current-step highlight."""
    icon, text_tpl, is_clickable, btn_type = _resolve_step_appearance(step_num, current_step)
    # Fill the step name placeholder in the template
    status_text = text_tpl.replace("{step}", step)

    if is_clickable and step_num != current_step:
        st.button(
            f"{icon} {status_text}",
            key=f"nav_step_{step_num}",
            width="stretch",
            type=btn_type,
            help=f"Go to Step {step_num}: {step}",
            on_click=_navigate_and_save,
            args=(step_num,),
        )
    elif not is_clickable and step_num != current_step:
        st.markdown(f"""
        <div style="background-color:#F1F5F9; border:1px solid #CBD5E1; border-radius:5px;
                    padding:10px; text-align:center; color:#94A3B8; cursor:not-allowed;">
            {icon} {step_num}. {step}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="background-color:#3B82F620; border:2px solid #3B82F6; border-radius:5px;
                    padding:10px; text-align:center; font-weight:bold; color:#3B82F6;">
            {icon} {step_num}. {step}
        </div>
        """, unsafe_allow_html=True)


def render_progress_indicator(current_step):
    """Render the 4-step progress indicator with clickable navigation and validation.

    Args:
        current_step (int): Current step number (1-4)
    """
    current_step = current_step or 1
    max_reached = st.session_state.get('dq_max_step_reached', 1) or 1
    if current_step > max_reached:
        st.session_state.dq_max_step_reached = current_step

    steps = ["Choose Data Source", "Configure Quality Controls", "Deploy DQ Job", "Run or Schedule Job"]
    cols = st.columns(len(steps))
    for idx, (col, step) in enumerate(zip(cols, steps)):
        with col:
            _render_step_indicator(idx + 1, step, current_step)
