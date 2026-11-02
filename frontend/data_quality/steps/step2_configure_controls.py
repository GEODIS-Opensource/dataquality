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

"""Step 2: Configure Quality Controls"""

import streamlit as st
import pandas as pd
from ..config import DQ_COMPONENTS, get_all_categories
from ..components import render_component_card, render_component_config


def _fetch_columns_from_api(job_id: int, source_type_hint) -> tuple:
    """Fetch column list and source type from the API for *job_id*.

    Returns ``(columns, source_type)``.  Also repopulates the relevant
    session-state keys when data is found.  On any error returns
    ``([], source_type_hint)`` so the caller can fall back gracefully.
    """
    import logging
    import json
    _log = logging.getLogger('dq_restore')
    _log.info(f"[RESTORE FALLBACK] No columns in session — fetching job {job_id} from API")
    try:
        from api_client import get_api_client
        api = get_api_client()
        result = api.get_job_details(job_id)
        if result.get('status') == 'success':
            job = result.get('job', result.get('data', {}))
            _sc = job.get('source_config', {})
            if isinstance(_sc, str):
                _sc = json.loads(_sc)
            if _sc:
                _nested = _sc.get('source_config') or {}
                columns = _nested.get('columns') or _sc.get('columns', [])
                source_type = source_type_hint or _sc.get('source_type') or _nested.get('source_type')
                # Repopulate session state
                st.session_state['dq_source_type'] = source_type
                st.session_state['dq_source_config'] = _nested if _nested else _sc
                st.session_state['dq_dataset_name'] = _sc.get('dataset_name')
                st.session_state['dq_dbfs_path'] = _sc.get('dbfs_path')
                _log.info(f"[RESTORE FALLBACK] Got {len(columns)} columns from API")
                return columns, source_type
    except Exception as e:
        _log.error(f"[RESTORE FALLBACK] API fetch failed: {e}")
    return [], source_type_hint


def _try_restore_dataset_preview():
    """Attempt to restore dq_dataset_preview from session state or API when it's missing."""
    # sc is always a dict thanks to the `or {}` fallback — no need to guard against None
    sc = st.session_state.get('dq_source_config') or {}
    source_type = sc.get('source_type') or st.session_state.get('dq_source_type')
    columns = sc.get('columns', [])

    # If we still don't have columns, try fetching fresh from the API
    if not columns:
        job_id = st.session_state.get('dq_current_job_id')
        if job_id:
            columns, source_type = _fetch_columns_from_api(job_id, source_type)

    if columns:
        st.session_state['dq_dataset_preview'] = pd.DataFrame(columns=columns)
        st.session_state['dq_df_columns_cache'] = columns
    elif source_type:
        st.session_state['dq_dataset_preview'] = pd.DataFrame()


def render_step2_configure_quality_controls():
    """Step 2: Configure data quality controls"""
    # If preview is missing but config exists or source type is set, try to restore it
    if st.session_state.get('dq_dataset_preview') is None:
        if st.session_state.get('dq_source_config') or st.session_state.get('dq_source_type') or st.session_state.get('dq_current_job_id'):
            _try_restore_dataset_preview()

    if st.session_state.dq_dataset_preview is not None:
        df = st.session_state.dq_dataset_preview
        dataset_name = st.session_state.get('dq_dataset_name', 'Dataset')
        
        st.info(f"📊 Configuring quality controls for: **{dataset_name}**")
        
        # Initialize selected components in session state
        if 'dq_selected_components' not in st.session_state:
            st.session_state.dq_selected_components = []
        if 'dq_component_configs' not in st.session_state:
            st.session_state.dq_component_configs = {}
        
        # Section 1: Choose Components
        _render_component_selection()
        
        # Section 2: Configure Selected Components
        if st.session_state.dq_selected_components:
            st.markdown("---")
            _render_component_configuration(df)
            
            # Section 3: Configure Thresholds
            st.markdown("---")
            _render_threshold_configuration()
        else:
            st.warning("⚠️ No components selected. Please choose at least one quality control component.")
        
        # Navigation
        _render_navigation()
    else:
        st.warning("⚠️ No dataset loaded. Please go back and configure your data source.")
        if st.button("← Back to Data Source"):
            st.session_state.dq_step = 1
            st.rerun()


def _toggle_component(component_id):
    """Callback to toggle component selection"""
    if component_id in st.session_state.dq_selected_components:
        st.session_state.dq_selected_components.remove(component_id)
        if component_id in st.session_state.dq_component_configs:
            del st.session_state.dq_component_configs[component_id]
    else:
        st.session_state.dq_selected_components.append(component_id)


def _render_component_selection():
    """Render component selection cards"""
    st.markdown("Select the components you want to apply to your dataset:")
    
    # Group components by category - cache this to avoid repeated iteration
    categories = get_all_categories()
    
    # Cache components by category for performance
    if 'dq_components_by_category' not in st.session_state:
        st.session_state.dq_components_by_category = {}
        for category in categories:
            st.session_state.dq_components_by_category[category] = [
                c for c in DQ_COMPONENTS if c['category'] == category
            ]
    
    # Map each category to the icon of its first component
    category_icons = {}
    for c in DQ_COMPONENTS:
        if c['category'] not in category_icons:
            category_icons[c['category']] = c['icon']

    for category in categories:
        icon = category_icons.get(category, "")
        st.markdown(f"##### {icon} {category}")
        components_in_category = st.session_state.dq_components_by_category[category]
        
        # Display components as cards in columns
        cols = st.columns(min(len(components_in_category), 3))
        
        for idx, component in enumerate(components_in_category):
            col_idx = idx % 3
            with cols[col_idx]:
                is_selected = component['id'] in st.session_state.dq_selected_components
                
                # Render card
                render_component_card(component, is_selected)
                
                # Handle toggle with callback
                if is_selected:
                    st.button(
                        f"✅ Selected", 
                        key=f"toggle_{component['id']}", 
                        width="stretch", 
                        type="primary",
                        on_click=_toggle_component,
                        args=(component['id'],)
                    )
                else:
                    st.button(
                        f"➕ Add Component", 
                        key=f"toggle_{component['id']}", 
                        width="stretch",
                        on_click=_toggle_component,
                        args=(component['id'],)
                    )


def _render_component_configuration(df):
    """Render configuration for selected components"""
    st.markdown("#### ⚙️ Configure Selected Components")
    
    # Get selected component objects - cache lookup by ID for performance
    if 'dq_components_by_id' not in st.session_state:
        st.session_state.dq_components_by_id = {c['id']: c for c in DQ_COMPONENTS}
    
    selected_component_objs = [
        st.session_state.dq_components_by_id[comp_id] 
        for comp_id in st.session_state.dq_selected_components
    ]
    
    for component in selected_component_objs:
        # Keep expanded=True as requested by user
        with st.expander(f"{component['icon']} {component['name']}", expanded=True):
            render_component_config(component, df)


def _render_threshold_target_sliders(
    component_id: str,
    target_name: str,
    target_key: str,
    widget_key: str,
    target_label: str,
) -> None:
    """Render the warning/OK slider pair for a single threshold target."""
    st.markdown(f"**{target_label}: `{target_name}`**")

    col1, col2 = st.columns(2)

    # Initialise threshold defaults for this target
    if target_key not in st.session_state.dq_thresholds[component_id]:
        st.session_state.dq_thresholds[component_id][target_key] = {'warning': 80, 'ok': 95}

    warn_key = f"warn_{component_id}_{widget_key}"
    ok_key = f"ok_{component_id}_{widget_key}"

    # Initialise slider widget state on first render
    if warn_key not in st.session_state:
        st.session_state[warn_key] = st.session_state.dq_thresholds[component_id][target_key]['warning']
    if ok_key not in st.session_state:
        st.session_state[ok_key] = st.session_state.dq_thresholds[component_id][target_key]['ok']

    with col1:
        st.slider("⚠️ Warning Threshold (%)", min_value=0, max_value=100,
                  value=st.session_state[warn_key], key=warn_key,
                  help="Values below this trigger a warning")
        st.session_state.dq_thresholds[component_id][target_key]['warning'] = st.session_state[warn_key]

    with col2:
        st.slider("✅ OK Threshold (%)", min_value=0, max_value=100,
                  value=st.session_state[ok_key], key=ok_key,
                  help="Values above this are considered OK")
        st.session_state.dq_thresholds[component_id][target_key]['ok'] = st.session_state[ok_key]

    # Visual indicator
    warning = st.session_state[warn_key]
    ok = st.session_state[ok_key]
    if warning >= ok:
        st.error("⚠️ Warning threshold must be lower than OK threshold")
    else:
        st.caption(f"🔴 < {warning}% | 🟡 {warning}%-{ok}% | 🟢 > {ok}%")

    st.markdown("---")


def _render_component_thresholds(component: dict) -> None:
    """Render all threshold controls for one component.

    Resolves the list of threshold targets (rules or columns), prunes stale
    entries for custom-rule components, then delegates each target's slider
    pair to :func:`_render_threshold_target_sliders`.
    """
    component_id = component['id']
    config = st.session_state.dq_component_configs.get(component_id, {})

    if component_id == 'accuracy_custom_rules':
        threshold_targets = [
            (rule.get('name') or f"Rule {idx + 1}", rule.get('name') or f"Rule {idx + 1}", f"rule_{idx + 1}")
            for idx, rule in enumerate(config.get('custom_rules', []))
            if isinstance(rule, dict)
        ]
        target_label = "Rule"
    else:
        from ..utils import extract_controlled_columns
        threshold_targets = [(col, col, col) for col in extract_controlled_columns(config)]
        target_label = "Column"

    if component_id not in st.session_state.dq_thresholds:
        st.session_state.dq_thresholds[component_id] = {}
    if component_id == 'accuracy_custom_rules':
        rule_names = {target_key for _, target_key, _ in threshold_targets}
        st.session_state.dq_thresholds[component_id] = {
            key: value
            for key, value in st.session_state.dq_thresholds[component_id].items()
            if key in rule_names
        }

    if threshold_targets:
        with st.expander(f"{component['icon']} {component['name']} - Thresholds", expanded=False):
            for target_name, target_key, widget_key in threshold_targets:
                _render_threshold_target_sliders(
                    component_id, target_name, target_key, widget_key, target_label
                )


def _render_threshold_configuration():
    """Render thresholds per rule for Custom Rules and per column otherwise."""
    st.markdown("#### 🎯 Configure Quality Thresholds")
    st.markdown("Set warning and OK thresholds for each rule or controlled column:")

    # Initialise thresholds in session state
    if 'dq_thresholds' not in st.session_state:
        st.session_state.dq_thresholds = {}

    # Get selected component objects — use cached dict lookup
    if 'dq_components_by_id' not in st.session_state:
        st.session_state.dq_components_by_id = {c['id']: c for c in DQ_COMPONENTS}

    selected_component_objs = [
        st.session_state.dq_components_by_id[comp_id]
        for comp_id in st.session_state.dq_selected_components
    ]

    for component in selected_component_objs:
        _render_component_thresholds(component)


def _render_navigation():
    """Render navigation buttons with validation and auto-save"""
    st.markdown("---")
    
    # Check if step 2 is complete (has selected components)
    has_selected_components = len(st.session_state.get('dq_selected_components', [])) > 0
    has_configs = len(st.session_state.get('dq_component_configs', {})) > 0
    is_step2_complete = has_selected_components and has_configs
    
    if not is_step2_complete:
        st.warning("⚠️ Please select and configure at least one quality control component before proceeding.")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        def _go_back_to_source():
            from ..projects import save_project_state
            save_project_state(async_save=False)
            st.session_state.dq_step = 1

        if st.button("← Back to Data Source", width="stretch", on_click=_go_back_to_source):
            pass
    with col2:
        # Only enable Next if step 2 is complete
        if is_step2_complete:
            def _go_to_deploy():
                # Persist the full step 2 state before leaving the page.
                from ..projects import save_project_state
                save_project_state(async_save=False)

                # Update job status to 'configured' before moving to step 3
                try:
                    from api_client import get_api_client
                    job_id = st.session_state.get('dq_current_job_id')
                    if job_id:
                        api_client = get_api_client()
                        api_client.update_job(job_id, {'status': 'configured', 'step': 3})
                except Exception as e:
                    st.warning(f"Could not update job status: {e}")

                st.session_state.dq_step = 3

            if st.button("Next: Deploy Job →", type="primary", width="stretch", on_click=_go_to_deploy):
                pass
        else:
            st.button("Next: Deploy Job →", type="primary", width="stretch", disabled=True,
                     help="Please configure at least one quality control component first")
