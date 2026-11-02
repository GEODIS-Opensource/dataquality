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

"""Component Configuration UI"""

import streamlit as st
from uuid import uuid4
import re

_NULL_OPS = ('is null', 'is not null')


@st.cache_data
def _get_dataframe_columns(df_hash):
    """Cache dataframe columns list for performance"""
    # df_hash is just for cache key, actual df is passed separately
    return None  # Placeholder, columns passed directly


def _get_cached_columns(df):
    """Get cached list of dataframe columns"""
    cache_key = 'dq_df_columns_cache'
    current_columns = df.columns.tolist()
    if (
        cache_key not in st.session_state
        or st.session_state[cache_key] != current_columns
    ):
        st.session_state[cache_key] = current_columns
    return st.session_state[cache_key]




_COLUMN_TYPE_OPTIONS = [
    "SIREN", "SIRET", "French VAT", "Email", "Phone",
    "Date YYYY-MM", "Date DD/MM/YYYY",
    "Integer", "Decimal", "String", "Boolean",
]


def _render_column_type_selectors(component_id: str, selected_columns: list, config: dict) -> None:
    """Render one type-selectbox per selected column and update config."""
    st.markdown("**Configure Expected Data Type for Each Column:**")
    for col in selected_columns:
        type_key = f"{component_id}_type_{col}"
        st.session_state.setdefault(type_key, config['column_types'].get(col, _COLUMN_TYPE_OPTIONS[0]))
        st.selectbox(
            f"Type for `{col}`",
            _COLUMN_TYPE_OPTIONS,
            index=_COLUMN_TYPE_OPTIONS.index(st.session_state[type_key]) if st.session_state[type_key] in _COLUMN_TYPE_OPTIONS else 0,
            key=type_key,
        )
        config['column_types'][col] = st.session_state[type_key]
    # Remove columns that were deselected
    for col in list(config['column_types'].keys()):
        if col not in selected_columns:
            del config['column_types'][col]


def _render_column_type_mapping(component_id, param, config, df):
    """Render column-type mapping for meaning validity."""
    st.markdown(f"**{param['label']}**")
    st.caption(param.get('description', ''))

    config.setdefault('column_types', {})

    columns_key = f"{component_id}_columns"
    st.session_state.setdefault(columns_key, list(config['column_types'].keys()))

    columns = _get_cached_columns(df)
    st.multiselect("Select Columns to Validate", columns,
                   default=st.session_state[columns_key], key=columns_key)

    selected_columns = st.session_state[columns_key]
    if selected_columns:
        _render_column_type_selectors(component_id, selected_columns, config)
    else:
        config['column_types'] = {}


def _render_multiselect(component_id, param, config, df):
    """Render multiselect input"""
    key = f"{component_id}_{param['name']}"

    # Resolve current options first so we can validate defaults against them
    columns = _get_cached_columns(df)

    # Initialize key if not exists
    if key not in st.session_state:
        st.session_state[key] = config.get(param['name'], [])

    # Drop stale defaults that no longer exist in the current datasource columns
    valid_defaults = [v for v in st.session_state[key] if v in columns]
    if valid_defaults != st.session_state[key]:
        st.session_state[key] = valid_defaults

    st.multiselect(
        param['label'],
        columns,
        default=st.session_state[key],
        help=param.get('description'),
        key=key
    )

    # Update config from session state
    config[param['name']] = st.session_state[key]


def _render_select(component_id, param, config, df):
    """Render select dropdown"""
    # Use cached columns if options not explicitly provided
    if 'options' in param:
        options = param['options']
    else:
        options = _get_cached_columns(df)
    
    key = f"{component_id}_{param['name']}"
    
    # Initialize with default value, ensure it's in options
    if key not in st.session_state or st.session_state[key] not in options:
        default_value = config.get(param['name'], options[0] if options else None)
        if default_value not in options:
            default_value = options[0] if options else None
        st.session_state[key] = default_value

    default_idx = 0
    if st.session_state[key] in options:
        default_idx = options.index(st.session_state[key])

    st.selectbox(
        param['label'],
        options,
        index=default_idx,
        help=param.get('description'),
        key=key
    )
    config[param['name']] = st.session_state[key]


def _render_slider(component_id, param, config):
    """Render slider input"""
    key = f"{component_id}_{param['name']}"
    
    # Initialize with default value
    if key not in st.session_state:
        st.session_state[key] = config.get(param['name'], param.get('default', 50))
    
    st.slider(
        param['label'],
        min_value=param.get('min', 0),
        max_value=param.get('max', 100),
        value=st.session_state[key],
        help=param.get('description'),
        key=key
    )
    config[param['name']] = st.session_state[key]


def _render_number(component_id, param, config):
    """Render number input"""
    value = st.number_input(
        param['label'],
        value=config.get(param['name'], param.get('default', 1.0)),
        help=param.get('description'),
        key=f"{component_id}_{param['name']}"
    )
    config[param['name']] = value


def _render_text(component_id, param, config):
    """Render text input"""
    value = st.text_input(
        param['label'],
        value=config.get(param['name'], ''),
        help=param.get('description'),
        key=f"{component_id}_{param['name']}"
    )
    config[param['name']] = value


def _render_radio(component_id, param, config):
    """Render radio button input"""
    options = param.get('options', [])
    default = param.get('default', options[0] if options else '')
    selected = st.radio(
        param['label'],
        options,
        index=options.index(config.get(param['name'], default)) if config.get(param['name'], default) in options else 0,
        help=param.get('description'),
        key=f"{component_id}_{param['name']}",
        horizontal=True
    )
    config[param['name']] = selected


def _render_file(component_id, param, config):
    """Render file uploader"""
    uploaded_file = st.file_uploader(
        param['label'],
        help=param.get('description'),
        key=f"{component_id}_{param['name']}"
    )
    if uploaded_file:
        config[param['name']] = uploaded_file.name


def _default_accuracy_rule():
    """Create a default empty accuracy rule."""
    return {
        'id': uuid4().hex[:8],
        'name': 'Rule 1',
        'conditions': [_default_accuracy_condition(first=True)],
        'blank_when_not_applicable': True,
        'enabled': True,
    }


def _default_accuracy_condition(first=False):
    """Create a default empty condition for an accuracy rule."""
    return {
        'id': uuid4().hex[:8],
        'connector': '' if first else 'AND',
        'left_column': '',
        'operator': '==',
        'right_mode': 'column',
        'right_column': '',
        'right_value': '',
    }


def _sql_column_name(column_name):
    """Quote a column name for Spark SQL."""
    if not column_name:
        return ''
    return f"`{str(column_name).replace('`', '``')}`"


def _format_literal(value):
    """Format a literal value for Spark SQL."""
    if value is None:
        return 'NULL'

    text = str(value).strip()
    if text == '':
        return "''"
    if re.fullmatch(r'-?\d+(\.\d+)?', text):
        return text
    if text.lower() in ('true', 'false'):
        return text.lower()

    return "'" + text.replace("'", "''") + "'"


def _literal_matches_type(value, value_type):
    """Check whether a literal value matches the selected condition type."""
    if value is None:
        return False

    text = str(value).strip()
    if text == '':
        return False

    value_type = (value_type or 'text').strip().lower()

    if value_type == 'numeric':
        return bool(re.fullmatch(r'-?\d+(\.\d+)?', text))
    if value_type == 'date':
        return bool(
            re.fullmatch(r'\d{2}-\d{2}-\d{4}', text)
            or re.fullmatch(r'\d{4}-\d{2}-\d{2}', text)
            or re.fullmatch(r'\d{2}/\d{2}/\d{4}', text)
        )

    return True


def _format_typed_literal(value, value_type):
    """Format a typed literal for Spark SQL."""
    value_type = (value_type or 'text').strip().lower()
    text = '' if value is None else str(value).strip()

    if value_type == 'numeric' and _literal_matches_type(text, 'numeric'):
        return text

    return _format_literal(text)


def _literal_type_warning(value, value_type):
    """Return a warning message when the literal does not match the selected type."""
    if value is None:
        return None

    text = str(value).strip()
    if text == '':
        return None

    value_type = (value_type or 'text').strip().lower()
    if value_type not in ('numeric', 'text', 'date'):
        value_type = 'text'

    if _literal_matches_type(text, value_type):
        return None

    if value_type == 'numeric':
        return 'Warning: numeric selected, but the value does not look numeric.'
    if value_type == 'date':
        return 'Warning: date selected, but the value does not look like a date (DD-MM-YYYY, YYYY-MM-DD, or DD/MM/YYYY).'

    return None


def _build_accuracy_condition_expression(condition):
    """Build a Spark SQL fragment from one guided condition."""
    left_column = condition.get('left_column', '')
    operator = (condition.get('operator', '==') or '==').strip().lower()
    right_mode = condition.get('right_mode', 'column')
    value_type = condition.get('right_value_type', 'text')

    if not left_column:
        return ''

    left_expr = _sql_column_name(left_column)

    if operator in _NULL_OPS:
        return f"{left_expr} {operator.upper()}"

    if right_mode == 'column':
        right_ref = condition.get('right_column', '')
        if not right_ref:
            return ''
        right_expr = _sql_column_name(right_ref)
    else:
        right_expr = _format_typed_literal(condition.get('right_value', ''), value_type)

    if operator in ('==', '='):
        return f"{left_expr} = {right_expr}"
    if operator == '!=':
        return f"{left_expr} != {right_expr}"
    if operator in ('>', '>=', '<', '<='):
        return f"{left_expr} {operator} {right_expr}"
    if operator == 'contains':
        return f"instr(cast({left_expr} as string), cast({right_expr} as string)) > 0"
    if operator == 'not contains':
        return f"instr(cast({left_expr} as string), cast({right_expr} as string)) = 0"

    return ''


def _condition_value_type_warning(condition):
    """Return a warning for a condition value/type mismatch, if any."""
    if condition.get('right_mode', 'column') != 'value':
        return None

    operator = (condition.get('operator', '==') or '==').strip().lower()
    if operator in _NULL_OPS:
        return None

    return _literal_type_warning(condition.get('right_value', ''), condition.get('right_value_type', 'text'))


def _build_accuracy_rule_expression(conditions):
    """Combine multiple conditions into one rule expression."""
    expression_parts = []

    for idx, condition in enumerate(conditions):
        fragment = _build_accuracy_condition_expression(condition)
        if not fragment:
            continue

        if idx == 0 or not expression_parts:
            expression_parts.append(f"({fragment})")
        else:
            connector = (condition.get('connector') or 'AND').strip().upper()
            if connector not in ('AND', 'OR'):
                connector = 'AND'
            expression_parts.append(f"{connector} ({fragment})")

    return ' '.join(expression_parts)


def _accuracy_rule_columns(conditions):
    """Return the list of columns referenced by a rule."""
    cols = []

    for condition in conditions:
        left_column = condition.get('left_column', '')
        right_mode = condition.get('right_mode', 'column')
        right_column = condition.get('right_column', '')

        if left_column:
            cols.append(left_column)
        if right_mode == 'column' and right_column:
            cols.append(right_column)

    seen = set()
    ordered = []
    for col in cols:
        if col and col not in seen:
            seen.add(col)
            ordered.append(col)
    return ordered


def _render_condition_value_type(condition_id, condition, component_id, rule_id):
    """Render the value type selector for a condition."""
    value_type_key = f"{component_id}_rule_{rule_id}_cond_{condition_id}_value_type"
    if value_type_key not in st.session_state:
        st.session_state[value_type_key] = condition.get('right_value_type', 'text')

    st.selectbox(
        "Value Type",
        ['numeric', 'text', 'date'],
        format_func=lambda x: x.capitalize(),
        index=['numeric', 'text', 'date'].index(st.session_state[value_type_key]) if st.session_state[value_type_key] in ['numeric', 'text', 'date'] else 1,
        key=value_type_key,
        label_visibility='collapsed',
        help="Type of the literal value in this condition"
    )

    return value_type_key


def _delete_custom_rule(component_id, rule_id):
    """on_click callback: remove a rule before Streamlit's natural rerun, avoiding a redundant extra rerun."""
    cfg = st.session_state.dq_component_configs.get(component_id, {})
    cfg['custom_rules'] = [r for r in cfg.get('custom_rules', []) if r.get('id') != rule_id]


def _delete_custom_rule_condition(rule_conditions_key, condition_id):
    """on_click callback: remove a condition before Streamlit's natural rerun, avoiding a redundant extra rerun."""
    conditions = [c for c in st.session_state.get(rule_conditions_key, []) if c.get('id') != condition_id]
    if not conditions:
        conditions = [_default_accuracy_condition(first=True)]
    st.session_state[rule_conditions_key] = conditions


def _add_custom_rule_condition(rule_conditions_key):
    """on_click callback: append a blank condition before Streamlit's natural rerun, avoiding a redundant extra rerun."""
    conditions = list(st.session_state.get(rule_conditions_key, []))
    conditions.append({
        'id': uuid4().hex[:8],
        'connector': 'AND',
        'left_column': '',
        'operator': '==',
        'right_mode': 'column',
        'right_column': '',
        'right_value': '',
    })
    st.session_state[rule_conditions_key] = conditions


def _ensure_rule_session_state(component_id: str, rule: dict, idx: int, rule_id: str,
                               rule_name_key: str, rule_blank_key: str,
                               rule_enabled_key: str, rule_conditions_key: str) -> None:
    """Initialise session-state keys for one rule if they are not already set."""
    st.session_state.setdefault(rule_name_key, rule.get('name', f'Rule {idx + 1}'))
    st.session_state.setdefault(rule_blank_key, rule.get('blank_when_not_applicable', True))
    st.session_state.setdefault(rule_enabled_key, rule.get('enabled', True))
    if rule_conditions_key not in st.session_state:
        conditions = rule.get('conditions', [])
        if not isinstance(conditions, list) or not conditions:
            conditions = [_default_accuracy_condition(first=True)]
        st.session_state[rule_conditions_key] = conditions


def _render_rule_header(component_id: str, rule_id: str, rule_name_key: str) -> None:
    """Render the rule name input and the delete button."""
    name_col, delete_col = st.columns([5, 0.55])
    with name_col:
        st.text_input("Rule Name", key=rule_name_key, help="Give this rule a short, readable name")
    with delete_col:
        st.markdown("<div style='height: 1.85rem;'></div>", unsafe_allow_html=True)
        st.button("🗑️", key=f"{component_id}_remove_{rule_id}", width="stretch",
                  help="Remove rule", on_click=_delete_custom_rule, args=(component_id, rule_id))


def _render_right_operand_widget(col, right_mode_key: str, operator_key: str,
                                  right_column_key: str, right_value_key: str,
                                  condition: dict, columns: list) -> None:
    """Render the right-operand cell: column selectbox, value input, or blank placeholder."""
    with col:
        right_mode_value = st.session_state.get(right_mode_key, condition.get('right_mode', 'column'))
        operator_value = st.session_state.get(operator_key, condition.get('operator', '=='))
        null_ops = _NULL_OPS
        if right_mode_value == 'column' and operator_value not in null_ops:
            right_column_value = st.session_state.get(right_column_key, condition.get('right_column', ''))
            st.selectbox("Right Column", [''] + columns,
                         index=([''] + columns).index(right_column_value) if right_column_value in ([''] + columns) else 0,
                         key=right_column_key, label_visibility='collapsed',
                         help="Second column of the condition")
        elif operator_value not in null_ops:
            st.session_state.setdefault(right_value_key, condition.get('right_value', ''))
            st.text_input("Right Value", key=right_value_key, label_visibility='collapsed',
                          help="Literal value to compare against")
        else:
            st.markdown("_")


def _render_condition_row(component_id: str, rule_id: str, rule_conditions_key: str,
                           cond_idx: int, condition: dict,
                           columns: list, operator_options: list) -> None:
    """Render one condition row (connector + 6 widgets + delete) and write state back to condition."""
    condition_id = condition.get('id') or uuid4().hex[:8]
    condition['id'] = condition_id

    prefix = f"{component_id}_rule_{rule_id}_cond_{condition_id}"
    connector_key      = f"{prefix}_connector"
    left_key           = f"{prefix}_left"
    operator_key       = f"{prefix}_operator"
    right_mode_key     = f"{prefix}_right_mode"
    right_value_type_key = f"{prefix}_right_value_type"
    right_column_key   = f"{prefix}_right_column"
    right_value_key    = f"{prefix}_right_value"

    if cond_idx > 0:
        st.session_state.setdefault(connector_key, condition.get('connector', 'AND'))
        connector_col, _ = st.columns([1.2, 6.0])
        with connector_col:
            cur = st.session_state.get(connector_key, condition.get('connector', 'AND'))
            st.selectbox("Connector", ['AND', 'OR'],
                         index=['AND', 'OR'].index(cur) if cur in ['AND', 'OR'] else 0,
                         key=connector_key, label_visibility='collapsed',
                         help="Connector between this condition and the previous one")

    row_cols = st.columns([2.0, 1.05, 1.0, 1.2, 2.0, 0.55])

    with row_cols[0]:
        left_value = st.session_state.get(left_key, condition.get('left_column', ''))
        st.selectbox("Left Column", [''] + columns,
                     index=([''] + columns).index(left_value) if left_value in ([''] + columns) else 0,
                     key=left_key, label_visibility='collapsed', help="First column of the condition")
    with row_cols[1]:
        vt = st.session_state.get(right_value_type_key, condition.get('right_value_type', 'text'))
        st.selectbox("Value Type", ['numeric', 'text', 'date'], format_func=lambda x: x.capitalize(),
                     index=['numeric', 'text', 'date'].index(vt) if vt in ['numeric', 'text', 'date'] else 1,
                     key=right_value_type_key, label_visibility='collapsed', help="Type of the literal value")
    with row_cols[2]:
        op = st.session_state.get(operator_key, condition.get('operator', '=='))
        st.selectbox("Operator", operator_options,
                     index=operator_options.index(op) if op in operator_options else 0,
                     key=operator_key, label_visibility='collapsed', help="Comparison operator")
    with row_cols[3]:
        rm = st.session_state.get(right_mode_key, condition.get('right_mode', 'column'))
        st.selectbox("Right Operand Type", ['column', 'value'],
                     format_func=lambda x: 'Column' if x == 'column' else 'Value',
                     index=0 if rm == 'column' else 1,
                     key=right_mode_key, label_visibility='collapsed',
                     help="Compare against another column or a literal value")

    _render_right_operand_widget(row_cols[4], right_mode_key, operator_key,
                                  right_column_key, right_value_key, condition, columns)

    with row_cols[5]:
        st.button("🗑️", key=f"{component_id}_remove_condition_{rule_id}_{condition_id}",
                  width="stretch", help="Remove condition",
                  on_click=_delete_custom_rule_condition, args=(rule_conditions_key, condition_id))

    # Write widget values back into condition dict
    condition['connector']        = '' if cond_idx == 0 else st.session_state[connector_key]
    condition['left_column']      = st.session_state[left_key]
    condition['operator']         = st.session_state[operator_key]
    condition['right_mode']       = st.session_state[right_mode_key]
    condition['right_value_type'] = st.session_state[right_value_type_key]
    condition['right_column']     = st.session_state.get(right_column_key, condition.get('right_column', ''))
    condition['right_value']      = st.session_state.get(right_value_key, condition.get('right_value', ''))

    warning_message = _condition_value_type_warning(condition)
    if warning_message:
        st.warning(warning_message)


def _render_rule_conditions(component_id: str, rule_id: str, rule_conditions_key: str,
                              columns: list, operator_options: list) -> list:
    """Render all conditions for a rule; return the updated conditions list."""
    st.markdown("##### Conditions")
    rule_conditions = st.session_state[rule_conditions_key]
    if not rule_conditions:
        rule_conditions = [_default_accuracy_condition(first=True)]
        st.session_state[rule_conditions_key] = rule_conditions

    updated_conditions = []
    for cond_idx, condition in enumerate(rule_conditions):
        _render_condition_row(component_id, rule_id, rule_conditions_key,
                               cond_idx, condition, columns, operator_options)
        updated_conditions.append(condition)

    add_button_col, _ = st.columns([0.45, 6.35])
    with add_button_col:
        st.button("➕", key=f"{component_id}_add_condition_{rule_id}", width="stretch",
                  help="Add condition", on_click=_add_custom_rule_condition, args=(rule_conditions_key,))

    preview_expression = _build_accuracy_rule_expression(updated_conditions)
    if preview_expression:
        st.code(preview_expression, language="sql")
    else:
        st.warning("This rule is incomplete. Add columns and operators to build the condition.")

    return updated_conditions, preview_expression


def _render_single_rule(component_id: str, rule: dict, idx: int,
                         columns: list, operator_options: list) -> None:
    """Render one complete rule block and write all widget values back into the rule dict."""
    rule_id = rule.get('id') or uuid4().hex[:8]
    rule['id'] = rule_id

    rule_name_key      = f"{component_id}_rule_name_{rule_id}"
    rule_blank_key     = f"{component_id}_rule_blank_{rule_id}"
    rule_enabled_key   = f"{component_id}_rule_enabled_{rule_id}"
    rule_conditions_key = f"{component_id}_rule_conditions_{rule_id}"

    _ensure_rule_session_state(component_id, rule, idx, rule_id,
                                rule_name_key, rule_blank_key, rule_enabled_key, rule_conditions_key)
    _render_rule_header(component_id, rule_id, rule_name_key)

    st.checkbox("Return blank when required columns are missing or empty", key=rule_blank_key,
                help="If one of the rule columns is missing or empty, the rule returns NULL instead of 0")
    st.checkbox("Enabled", key=rule_enabled_key, help="Disable this rule without deleting it")

    updated_conditions, preview_expression = _render_rule_conditions(
        component_id, rule_id, rule_conditions_key, columns, operator_options)

    rule['name']                    = st.session_state[rule_name_key]
    rule['conditions']              = updated_conditions
    rule['columns']                 = _accuracy_rule_columns(updated_conditions)
    rule['blank_when_not_applicable'] = st.session_state[rule_blank_key]
    rule['enabled']                 = st.session_state[rule_enabled_key]
    rule['condition']               = preview_expression


def _render_custom_rules_builder(component_id, param, config, df):
    """Render a builder for custom if/then accuracy rules"""
    st.markdown(f"**{param['label']}**")
    st.caption(param.get('description', ''))

    if 'custom_rules' not in config or not isinstance(config.get('custom_rules'), list):
        config['custom_rules'] = []

    columns = _get_cached_columns(df)
    operator_options = ['==', '!=', '>', '>=', '<', '<=', *_NULL_OPS]

    add_col, remove_col = st.columns([1, 4])
    with add_col:
        if st.button("➕ Add Rule", key=f"{component_id}_add_rule", width="stretch"):
            rule = _default_accuracy_rule()
            rule['name'] = f'Rule {len(config["custom_rules"]) + 1}'
            config['custom_rules'].append(rule)
            st.session_state.dq_component_configs[component_id] = config
    with remove_col:
        st.markdown("&nbsp;")

    if not config['custom_rules']:
        st.info("No custom rules defined yet. Click **Add Rule** to create one.")

    updated_rules = []
    for idx, rule in enumerate(config['custom_rules']):
        _render_single_rule(component_id, rule, idx, columns, operator_options)
        updated_rules.append(rule)
    config['custom_rules'] = updated_rules


# ── Dispatch tables ────────────────────────────────────────────────────────────
# Defined after all _render_* helpers so every function is already in scope.
_PARAM_RENDERERS_WITH_DF = {
    'column_type_mapping':  _render_column_type_mapping,
    'multiselect':          _render_multiselect,
    'select':               _render_select,
    'custom_rules_builder': _render_custom_rules_builder,
}
_PARAM_RENDERERS_NO_DF = {
    'slider': _render_slider,
    'number': _render_number,
    'text':   _render_text,
    'radio':  _render_radio,
    'file':   _render_file,
}


def _param_is_visible(param: dict, config: dict) -> bool:
    """Return False when a show_if condition hides this parameter."""
    if 'show_if' not in param:
        return True
    return all(config.get(k) == v for k, v in param['show_if'].items())


def _dispatch_param_renderer(component_id: str, param: dict, config: dict, df) -> None:
    """Call the appropriate renderer for the given param type."""
    ptype = param['type']
    if ptype in _PARAM_RENDERERS_WITH_DF:
        _PARAM_RENDERERS_WITH_DF[ptype](component_id, param, config, df)
    elif ptype in _PARAM_RENDERERS_NO_DF:
        _PARAM_RENDERERS_NO_DF[ptype](component_id, param, config)


def render_component_config(component, df):
    """Render configuration UI for a specific component.

    Args:
        component (dict): Component configuration
        df (DataFrame): Dataset to analyze
    """
    component_id = component['id']
    st.session_state.dq_component_configs.setdefault(component_id, {})
    config = st.session_state.dq_component_configs[component_id]

    for param in component['params']:
        if not _param_is_visible(param, config):
            continue
        _dispatch_param_renderer(component_id, param, config, df)

    st.session_state.dq_component_configs[component_id] = config
