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

"""Step 1: Choose Data Source"""

import streamlit as st
import pandas as pd
import sys
import os
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from api_client import get_api_client

_NEXT_STEP_LABEL = "Next: Configure Quality Controls →"


# ── Top-level entry point ─────────────────────────────────────────────────────

def render_step1_choose_source():
    """Step 1: Choose data source"""

    _render_selected_source_banner()

    # Source type selection - restore previous choice from session state
    _default_source_index = 1 if st.session_state.get('dq_source_type') == 'unity_catalog' else 0
    source_type = st.radio(
        "Source Type",
        ["📄 CSV Import", "🌟 Unity Catalog"],
        index=_default_source_index,
        horizontal=True,
    )

    st.markdown("---")

    if source_type == "📄 CSV Import":
        st.session_state.dq_source_type = "csv"
        _render_csv_source_config()
    else:
        st.session_state.dq_source_type = "unity_catalog"
        _render_unity_catalog_source_config()


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _render_selected_source_banner() -> None:
    """Display the currently-selected source name above the source-type radio."""
    sc = st.session_state.get('dq_source_config')
    if not sc:
        return
    if sc.get('source_type') == 'csv':
        dataset_name = (
            sc['source_config'].get('dataset_name')
            if isinstance(sc.get('source_config'), dict)
            else None
        ) or sc.get('dataset_name') or sc.get('file_name') or 'None'
        st.info(f"📝 Selected source: {dataset_name}")
    elif sc.get('source_type') == 'unity_catalog':
        st.info(
            f"📝 Selected source: "
            f"{sc.get('catalog', '')}.{sc.get('schema', '')}.{sc.get('table', '')}"
        )


def _normalize_csv_config() -> None:
    """Flatten a nested source_config dict (as loaded from DB) into session state."""
    raw = st.session_state.get('dq_source_config') or {}
    inner = raw.get('source_config')
    if not isinstance(inner, dict):
        return
    flat = {**inner}
    flat['volume_path'] = raw.get('volume_path') or inner.get('volume_path')
    flat['dataset_name'] = raw.get('dataset_name') or inner.get('dataset_name', '')
    st.session_state.dq_source_config = flat


def _restore_csv_preview_state() -> None:
    """Re-seed CSV preview state when returning from another step or re-opening a job."""
    if st.session_state.get('existing_csv_loaded', False):
        return
    cfg = st.session_state.get('dq_source_config') or {}
    if cfg.get('source_type') != 'csv':
        return

    dbfs_path = cfg.get('volume_path') or st.session_state.get('dq_dbfs_path')
    file_name = cfg.get('file_name', cfg.get('dataset_name', 'Selected file'))
    preview = st.session_state.get('dq_dataset_preview')
    has_preview = preview is not None and not (hasattr(preview, 'empty') and preview.empty)

    if has_preview:
        # Real preview in memory (navigated between steps within same session)
        if not st.session_state.get('selected_csv_name'):
            st.session_state.selected_csv_name = file_name
        if dbfs_path and not st.session_state.get('selected_csv_path'):
            st.session_state.selected_csv_path = dbfs_path
        st.session_state.existing_csv_loaded = True
    elif dbfs_path:
        # Preview lost (job re-opened or page refreshed) but Volume path known
        st.session_state.selected_csv_path = dbfs_path
        st.session_state.selected_csv_name = file_name
        st.session_state.existing_csv_loaded = True


def _render_csv_file_row(idx: int, file: dict) -> None:
    """Render a single row in the existing-files list."""

    def _select_file(path, name):
        st.session_state.selected_csv_path = path
        st.session_state.selected_csv_name = name
        st.session_state.load_existing_csv = True

    col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 1.5, 1])
    with col1:
        st.markdown(f"**{file['name']}**")
    with col2:
        st.text(f"{file['size_kb']} KB")
    with col3:
        if file.get('modified_at'):
            mod_time = datetime.fromtimestamp(file['modified_at'] / 1000)
            st.text(mod_time.strftime("%Y-%m-%d %H:%M"))
    with col4:
        st.button(
            "📥 Use", key=f"use_csv_{idx}", width="stretch",
            on_click=_select_file, args=(file['path'], file['name']),
        )
    with col5:
        if st.button("🗑️", key=f"delete_csv_{idx}", help="Delete file", width="stretch"):
            st.session_state.file_to_delete = file
            st.session_state.show_delete_confirmation = True
            st.rerun()


def _execute_csv_delete(api_client, project_id: str, file_to_delete: dict) -> None:
    """Call the API to delete *file_to_delete* and refresh the file list."""
    with st.spinner(f"Deleting {file_to_delete['name']}..."):
        result = api_client.delete_csv_file(
            project_id=project_id,
            file_path=file_to_delete['path'],
            user_email=st.session_state.get('current_user'),
        )
    if result.get('status') == 'success':
        st.toast(f"{file_to_delete['name']} deleted successfully!", icon="✅")
        st.session_state.show_delete_confirmation = False
        st.session_state.file_to_delete = None
        st.session_state.pop(f'dq_csv_files_{project_id}', None)
        st.rerun()
    else:
        st.error(f"❌ {result.get('message', 'Deletion failed')}")


def _render_delete_confirmation(api_client, project_id: str) -> None:
    """Render the delete-confirmation modal and handle Yes / Cancel."""
    if not st.session_state.get('show_delete_confirmation', False):
        return

    file_to_delete = st.session_state.file_to_delete
    st.markdown("---")
    st.warning("⚠️ **Confirm Deletion**")
    st.markdown(f"Are you sure you want to delete **{file_to_delete['name']}**?")
    st.markdown("This action cannot be undone.")
    col1, col2, _ = st.columns([1, 1, 2])
    with col1:
        if st.button("✅ Yes, Delete", type="primary", width="stretch"):
            _execute_csv_delete(api_client, project_id, file_to_delete)
    with col2:
        if st.button("❌ Cancel", width="stretch"):
            st.session_state.show_delete_confirmation = False
            st.session_state.file_to_delete = None
            st.rerun()
    st.markdown("---")


def _render_existing_csv_files(api_client, project_id: str) -> None:
    """Render the 'Files Uploaded' expander with file rows and delete confirmation."""
    st.markdown("""
    <style>
    details[data-testid="stExpander"] summary p { font-size: 0.9rem; font-weight: 700; }
    </style>
    """, unsafe_allow_html=True)

    with st.expander("📂 Files Uploaded", expanded=False):
        cache_key = f'dq_csv_files_{project_id}'
        if cache_key not in st.session_state:
            with st.spinner("Loading existing files..."):
                st.session_state[cache_key] = api_client.list_csv_files(
                    project_id, user_email=st.session_state.get('current_user', '')
                )
        existing_files = st.session_state[cache_key]

        if not existing_files:
            st.info("📭 No CSV files uploaded yet for this project.")
            return

        st.info(f"📊 {len(existing_files)} file(s) found in Volume for this project")
        for idx, file in enumerate(existing_files):
            _render_csv_file_row(idx, file)

        _render_delete_confirmation(api_client, project_id)


def _fetch_and_cache_csv_preview(
    api_client, project_id: str, path: str, cache_key: str
) -> None:
    """Fetch CSV preview from backend, cache it, and update session state."""
    file_name = st.session_state.selected_csv_name
    with st.spinner(f"Loading {file_name}..."):
        result = api_client.preview_csv_from_dbfs(project_id=project_id, file_path=path)

    if result.get('status') != 'success':
        st.error(f"❌ Failed to load preview: {result.get('message', 'Unknown error')}")
        return

    stats = result['stats']
    config = result.get('config', {})
    df = pd.DataFrame(result['preview'])
    dataset_name = config.get('dataset_name', file_name.rsplit('.', 1)[0])

    source_config = {
        'source_type': 'csv',
        'dataset_name': dataset_name,
        'file_name': file_name,
        'separator': config.get('separator', ','),
        'quote_char': config.get('quote_char', '"'),
        'has_header': config.get('has_header', True),
        'skip_lines': config.get('skip_lines', 0),
        'volume_path': path,
        'columns': stats.get('columns', []),
        'row_count': stats['row_count'],
        'column_count': stats['column_count'],
    }

    st.session_state[cache_key] = {
        'df': df,
        'dataset_name': dataset_name,
        'volume_path': path,
        'config': source_config,
    }
    st.session_state.dq_dataset_preview = df
    st.session_state.dq_dataset_name = dataset_name
    st.session_state.dq_dbfs_path = path
    st.session_state.dq_source_type = 'csv'
    st.session_state.existing_csv_loaded = True
    st.session_state.dq_source_config = source_config
    # Cache columns list for Step 2 performance
    st.session_state.dq_df_columns_cache = df.columns.tolist()


def _load_selected_csv_from_cache(api_client, project_id: str) -> None:
    """Load a selected existing CSV file (from cache or API) into session state."""
    if not st.session_state.get('load_existing_csv', False):
        return
    st.session_state.load_existing_csv = False

    path = st.session_state.selected_csv_path
    cache_key = f'csv_preview_{path}'

    if cache_key in st.session_state:
        cached = st.session_state[cache_key]
        st.session_state.dq_dataset_preview = cached['df']
        st.session_state.dq_dataset_name = cached['dataset_name']
        st.session_state.dq_dbfs_path = cached['volume_path']
        st.session_state.dq_source_type = 'csv'
        st.session_state.existing_csv_loaded = True
        st.session_state.dq_source_config = cached['config']
        return

    _fetch_and_cache_csv_preview(api_client, project_id, path, cache_key)


def _render_loaded_csv_info() -> None:
    """Show file info, preview, and navigation buttons for a loaded CSV."""
    if not st.session_state.get('existing_csv_loaded', False):
        return

    df = st.session_state.get('dq_dataset_preview')
    config = st.session_state.dq_source_config
    st.info(f"✅ File: {st.session_state.get('selected_csv_name', config.get('file_name', ''))}")

    st.markdown("#### 📊 File Information")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Rows", f"{config['row_count']:,}")
    with col2:
        st.metric("Columns", config['column_count'])
    with col3:
        st.metric("Size", f"{config.get('file_size', 0) / 1024:.1f} KB")

    st.markdown("#### 👁️ Dataset Preview")
    has_data = df is not None and not (hasattr(df, 'empty') and df.empty)
    if has_data:
        st.dataframe(df.head(10), width="stretch")
    else:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.info("👆 Click 'Load Preview' to view file data.")
        with col2:
            if st.button("👁️ Load Preview", width="stretch", type="secondary"):
                st.session_state.load_existing_csv = True
                st.rerun()

    st.markdown("#### ⚙️ Configuration")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Dataset Name", value=config.get('dataset_name', ''), disabled=True, key="existing_dataset_name")
        st.text_input("Separator", value=config.get('separator', ','), disabled=True, key="existing_separator")
        st.text_input("Skip Lines", value=str(config.get('skip_lines', 0)), disabled=True, key="existing_skip_lines")
    with col2:
        st.text_input("Quote Character", value=config.get('quote_char', '"'), disabled=True, key="existing_quote_char")
        st.checkbox("Has Header", value=config.get('has_header', True), disabled=True, key="existing_has_header")

    st.markdown("---")
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("← Back", width="stretch", key="existing_csv_back"):
            st.session_state.existing_csv_loaded = False
            st.rerun()
    with col2:
        if st.button(_NEXT_STEP_LABEL, type="primary", width="stretch", key="existing_csv_next"):
            st.session_state.dq_step = 2
            st.rerun()

    st.markdown("---")
    st.markdown("##### ⬆️ Upload a New CSV File")


def _read_upload_format_config(uploaded_file) -> tuple:
    """Render file-format widgets; return (dataset_name, dataset_type, separator, skip_lines, quote_char, parse_headers)."""
    default_name = uploaded_file.name.rsplit('.', 1)[0]
    dataset_name = st.text_input("Dataset Name", value=default_name, help="Enter a name for this dataset")

    st.markdown("#### ⚙️ File Format Configuration")
    col1, col2 = st.columns(2)
    with col1:
        dataset_type = st.selectbox(
            "Dataset Type", ["CSV", "JSON", "Avro", "Delta Lake"],
            help="Select the format of your dataset",
        )
        separator = st.selectbox(
            "Field Separator", [",", ";", "Tab", "|", "Custom"],
            help="Character used to separate fields",
        )
        if separator == "Custom":
            separator = st.text_input("Custom Separator", value=",", max_chars=5)
        elif separator == "Tab":
            separator = "\t"
        skip_lines = st.number_input(
            "Skip First Lines", min_value=0, max_value=100, value=0,
            help="Number of lines to skip at the beginning of the file",
        )
    with col2:
        st.selectbox(
            "Quoting Style", ["Excel Style", "Unix Style", "Minimal", "All Fields"],
            help="How fields are quoted in the file",
        )
        quote_char = st.text_input(
            "Quoting Character", value='"', max_chars=1,
            help="Character used for quoting fields",
        )
        parse_headers = st.checkbox(
            "Parse Next Line as Column Headers", value=True,
            help="Use the first line (after skipped lines) as column names",
        )
    return dataset_name, dataset_type, separator, skip_lines, quote_char, parse_headers


def _execute_csv_upload(api_client, project_id, uploaded_file) -> None:
    """Call the API to upload *uploaded_file* to the Databricks Volume."""
    if not project_id:
        st.error("❌ No project selected. Please create or select a project first.")
        return
    with st.spinner("Uploading CSV file to Volume..."):
        try:
            result = api_client.upload_csv(
                project_id=project_id,
                file=uploaded_file,
                config=st.session_state.dq_source_config,
                user_email=st.session_state.get('current_user', ''),
            )
        except Exception as e:
            st.error(f"❌ Upload failed: {str(e)}")
            st.exception(e)
            return

    if result.get('status') == 'success':
        volume_path = result.get('volume_path')
        st.session_state.dq_dbfs_path = volume_path
        st.session_state.csv_file_metadata = result.get('file_metadata')
        st.session_state.csv_uploaded_to_dbfs = True

        # Bust stale caches so the new file's columns are always used
        # (same-filename re-uploads would otherwise return old columns from cache)
        st.session_state.pop(f'csv_preview_{volume_path}', None)
        st.session_state.pop(f'dq_csv_files_{project_id}', None)

        # Also refresh the columns cache from the new file metadata
        new_columns = (result.get('file_metadata') or {}).get('columns', [])
        if new_columns:
            st.session_state.dq_df_columns_cache = new_columns

        st.toast(f"File uploaded successfully to {volume_path}!", icon="✅")
        st.info("💾 File will be saved to project when you click Next.")
        st.balloons()
        st.rerun()
    else:
        st.error(f"❌ Upload failed: {result.get('message', 'Unknown error')}")


def _render_upload_or_next_buttons(api_client, project_id, uploaded_file) -> None:
    """Show Upload-to-Volume button, or Next button when file is already uploaded."""
    if st.session_state.get('csv_uploaded_to_dbfs', False):
        st.toast("✅ File uploaded successfully", icon="✅")
        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("🔄 Upload Again", width="stretch", key="upload_again"):
                st.session_state.csv_uploaded_to_dbfs = False
                st.rerun()
        with col2:
            if st.button(_NEXT_STEP_LABEL, type="primary", width="stretch", key="new_csv_next"):
                st.session_state.dq_step = 2
                st.rerun()
        return

    if st.button("📤 Upload to Volume", type="primary", width="stretch"):
        _execute_csv_upload(api_client, project_id, uploaded_file)
    st.info("💡 Please upload the file to Volume before proceeding to the next step.")


def _render_csv_preview_and_upload(
    api_client, project_id, uploaded_file,
    dataset_name, dataset_type, separator, skip_lines, quote_char, parse_headers,
) -> None:
    """Parse the uploaded CSV, show preview metrics, then render upload/next buttons."""
    if dataset_type != "CSV":
        st.info(f"📝 {dataset_type} parsing will be implemented in backend integration")
        return

    try:
        df = pd.read_csv(
            uploaded_file, sep=separator, quotechar=quote_char,
            skiprows=skip_lines, header=0 if parse_headers else None,
        )
        uploaded_file.seek(0)
    except Exception as e:
        st.error(f"❌ Error loading file: {str(e)}")
        return

    st.session_state.dq_dataset_preview = df
    st.session_state.dq_dataset_name = dataset_name
    # Cache columns list for Step 2 performance
    st.session_state.dq_df_columns_cache = df.columns.tolist()

    st.markdown("#### 👁️ Dataset Preview")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Rows", f"{len(df):,}")
    with col2:
        st.metric("Columns", len(df.columns))
    with col3:
        st.metric("Size", f"{uploaded_file.size / 1024:.1f} KB")
    st.dataframe(df.head(10), width="stretch")

    st.session_state.dq_source_config = {
        'source_type': 'csv',
        'dataset_name': dataset_name,
        'file_name': uploaded_file.name,
        'file_size': uploaded_file.size,
        'separator': separator,
        'quote_char': quote_char,
        'has_header': parse_headers,
        'skip_lines': skip_lines,
        'dataset_type': dataset_type,
        'columns': list(df.columns),
        'row_count': len(df),
        'column_count': len(df.columns),
    }

    st.markdown("---")
    _render_upload_or_next_buttons(api_client, project_id, uploaded_file)


def _render_csv_source_config():
    """Configure CSV data source (orchestrator — delegates to focused helpers)."""
    st.markdown("#### 📄 CSV Import Configuration")
    st.markdown(
        "Upload a new CSV file using **Upload CSV file**, or select a file you have already uploaded from **Files uploaded**."
    )

    api_client = get_api_client()
    _normalize_csv_config()
    _restore_csv_preview_state()

    project_id = (
        st.session_state.get('dq_current_project_id')
        or st.session_state.get('current_project_id')
    )
    if project_id:
        _render_existing_csv_files(api_client, project_id)
        st.markdown("---")
        st.markdown("##### ⬆️ Upload New CSV File")

    _load_selected_csv_from_cache(api_client, project_id)
    _render_loaded_csv_info()

    uploaded_file = st.file_uploader(
        "Upload your CSV file",
        type=["csv", "txt", "json", "avro"],
        help="Supported formats: CSV, JSON, Avro, Delta Lake",
    )
    if not uploaded_file:
        return

    st.session_state.dq_uploaded_file = uploaded_file
    dataset_name, dataset_type, separator, skip_lines, quote_char, parse_headers = \
        _read_upload_format_config(uploaded_file)
    _render_csv_preview_and_upload(
        api_client, project_id, uploaded_file,
        dataset_name, dataset_type, separator, skip_lines, quote_char, parse_headers,
    )


# ── Unity Catalog helpers ─────────────────────────────────────────────────────

def _restore_uc_session_state(sc: dict) -> None:
    """Re-seed UC widget keys from *sc* when Streamlit cleared them on navigation."""
    if sc.get('source_type') != 'unity_catalog':
        return
    if not st.session_state.get('dq_unity_catalog') and sc.get('catalog'):
        st.session_state.dq_unity_catalog = sc['catalog']
    if not st.session_state.get('dq_unity_schema') and sc.get('schema'):
        st.session_state.dq_unity_schema = sc['schema']
    if not st.session_state.get('dq_unity_table') and sc.get('table'):
        st.session_state.dq_unity_table = sc['table']


def _render_catalog_selector(api_client) -> str | None:
    """Load catalogs and render the catalog selectbox.

    Clears downstream state on change.
    Returns the selected catalog, or *None* when no catalogs are available.
    """
    # Fetch catalogs from backend (global cache — catalogs rarely change)
    if 'dq_available_catalogs' not in st.session_state:
        with st.spinner("Loading catalogs..."):
            st.session_state.dq_available_catalogs = api_client.get_catalogs()

    available_catalogs = st.session_state.dq_available_catalogs
    if not available_catalogs:
        st.warning("⚠️ No catalogs available. Check your Unity Catalog connection.")
        return None

    current_catalog = st.session_state.get('dq_unity_catalog')
    default_index = (
        available_catalogs.index(current_catalog)
        if current_catalog and current_catalog in available_catalogs
        else 0
    )
    selected_catalog = st.selectbox(
        "Catalog", available_catalogs, index=default_index,
        key="unity_catalog_selector", help="Select the Unity Catalog to use",
    )

    # Detect catalog change — clear downstream selections
    if st.session_state.get('dq_unity_catalog') != selected_catalog:
        st.session_state.dq_unity_catalog = selected_catalog
        for key in ('dq_unity_schema', 'dq_unity_table', 'dq_dataset_preview',
                    'dq_dataset_name', 'dq_df_columns_cache'):
            st.session_state.pop(key, None)
        for k in [k for k in st.session_state if k.startswith('dq_tables_')]:
            st.session_state.pop(k, None)

    return selected_catalog


def _render_schema_selector(api_client, catalog: str) -> str | None:
    """Load schemas for *catalog* and render the schema selectbox.

    Clears downstream state on change.
    Returns the selected schema, or *None* when no schemas are available.
    """
    cache_key = f'dq_schemas_{catalog}'
    if cache_key not in st.session_state:
        with st.spinner("Loading schemas..."):
            st.session_state[cache_key] = api_client.get_schemas(catalog)

    available_schemas = st.session_state[cache_key]
    if not available_schemas:
        st.warning("⚠️ No schemas available in this catalog.")
        return None

    current_schema = st.session_state.get('dq_unity_schema')
    default_index = (
        available_schemas.index(current_schema)
        if current_schema and current_schema in available_schemas
        else 0
    )
    selected_schema = st.selectbox(
        "Schema", available_schemas, index=default_index,
        key="unity_schema_selector", help="Select the schema within the catalog",
    )

    # Detect schema change — clear downstream selections
    if st.session_state.get('dq_unity_schema') != selected_schema:
        st.session_state.dq_unity_schema = selected_schema
        for key in ('dq_unity_table', 'dq_dataset_preview', 'dq_dataset_name', 'dq_df_columns_cache'):
            st.session_state.pop(key, None)

    return selected_schema


def _render_table_selector(api_client, catalog: str, schema: str) -> str | None:
    """Load tables for *catalog.schema* and render the table selectbox.

    Clears downstream state on change.
    Returns the selected table, or *None* when no tables are available.
    """
    cache_key = f'dq_tables_{catalog}_{schema}'
    if cache_key not in st.session_state:
        with st.spinner("Loading tables..."):
            st.session_state[cache_key] = api_client.get_tables(catalog, schema)

    available_tables = st.session_state[cache_key]
    if not available_tables:
        st.warning("⚠️ No tables available in this schema.")
        return None

    current_table = st.session_state.get('dq_unity_table')
    default_index = (
        available_tables.index(current_table)
        if current_table and current_table in available_tables
        else 0
    )
    selected_table = st.selectbox(
        "Table", available_tables, index=default_index,
        key="unity_table_selector", help="Select the table to analyze",
    )

    # Detect table change — clear preview
    if st.session_state.get('dq_unity_table') != selected_table:
        st.session_state.dq_unity_table = selected_table
        for key in ('dq_dataset_preview', 'dq_dataset_name'):
            st.session_state.pop(key, None)

    return selected_table


def _handle_preview_error(preview_data: dict, table_fqn: str) -> None:
    """Render the appropriate error UI for a failed preview request."""
    if preview_data.get('permission_error'):
        st.error("⛔ **Insufficient Permissions**")
        st.warning(
            f"You do not have **SELECT** privilege on table `{table_fqn}`.\n\n"
            "**Required permissions:** SELECT or ALL PRIVILEGES\n\n"
            "**Action:** Contact your Unity Catalog administrator to grant you SELECT access to this table."
        )
        # Clear any previous preview to prevent proceeding to Step 2
        if 'dq_dataset_preview' in st.session_state:
            del st.session_state.dq_dataset_preview
        if 'dq_source_config' in st.session_state:
            del st.session_state.dq_source_config
        # Don't stop — let the rest of the page render
    else:
        error_msg = preview_data.get('message', 'Unknown error')
        st.error(f"❌ Failed to load preview: {error_msg}")
        if 'dq_dataset_preview' in st.session_state:
            del st.session_state.dq_dataset_preview


def _build_preview_df(preview_data: dict) -> pd.DataFrame:
    """Convert API *preview_data* to a :class:`~pandas.DataFrame`."""
    preview = preview_data.get('preview')
    if preview:
        if preview.get('sample_data'):
            return pd.DataFrame(preview['sample_data'])
        # Create empty DataFrame with column names only
        return pd.DataFrame(columns=preview.get('columns', []))
    return pd.DataFrame()


def _save_preview_to_session(df: pd.DataFrame, catalog: str, schema: str, table: str) -> None:
    """Persist a loaded preview and its metadata to session state."""
    st.session_state.dq_dataset_preview = df
    st.session_state.dq_dataset_name = f"{catalog}.{schema}.{table}"
    st.session_state.dq_catalog = catalog
    st.session_state.dq_schema = schema
    st.session_state.dq_table = table
    st.session_state.dq_unity_catalog = catalog
    st.session_state.dq_unity_schema = schema
    st.session_state.dq_unity_table = table
    # Save columns and metadata for compatibility with Step 2/3
    st.session_state.dq_df_columns_cache = df.columns.tolist()
    st.session_state.dq_source_config = {
        'source_type': 'unity_catalog',
        'catalog': catalog,
        'schema': schema,
        'table': table,
        'columns': df.columns.tolist(),
        'row_count': len(df),
        'column_count': len(df.columns),
    }


def _handle_preview_button(api_client, catalog: str, schema: str, table: str) -> None:
    """Render the Load / Refresh Preview button and handle its click."""
    preview_exists = st.session_state.get('dq_dataset_preview') is not None
    button_label = "🔄 Refresh Preview" if preview_exists else "👁️ Load Preview"
    if not st.button(button_label, width="stretch", type="secondary"):
        return
    with st.spinner("Loading table preview..."):
        try:
            preview_data = api_client.preview_table(catalog, schema, table)
            if preview_data.get('status') == 'error':
                _handle_preview_error(preview_data, f"{catalog}.{schema}.{table}")
                return
            df = _build_preview_df(preview_data)
            _save_preview_to_session(df, catalog, schema, table)
            st.toast("Preview loaded successfully!", icon="✅")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Failed to load preview: {str(e)}")


def _render_table_preview() -> None:
    """Show the table-preview section, or an invitation to load one."""
    df = st.session_state.get('dq_dataset_preview')
    if df is None:
        st.info("👆 Click 'Load Preview' to view table data and proceed to the next step.")
        return

    st.markdown("---")
    st.markdown("#### 👁️ Table Preview")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📊 Rows (preview)", f"{len(df):,}")
    with col2:
        st.metric("📋 Columns", len(df.columns))
    with col3:
        st.metric("📚 Source", "Unity Catalog")

    st.dataframe(df.head(20), width="stretch", height=400)

    with st.expander("📋 Column Details", expanded=False):
        col_df = pd.DataFrame({
            'Column': df.columns,
            'Type': df.dtypes.astype(str),
            'Non-Null': df.count(),
            'Null': df.isnull().sum(),
        })
        st.dataframe(col_df, width="stretch")

    st.markdown("---")
    if st.button(_NEXT_STEP_LABEL, type="primary", width="stretch"):
        st.session_state.dq_step = 2
        st.rerun()


# ── Orchestrator ──────────────────────────────────────────────────────────────

def _render_unity_catalog_source_config():
    """Configure Unity Catalog data source."""
    st.markdown("#### 🌟 Unity Catalog Configuration")
    st.markdown(
        "Select the **Catalog**, **Schema**, and **Table** you want to analyze. "
        "Only assets you have been granted access to will be visible."
    )

    api_client = get_api_client()
    # Streamlit clears widget state for keys not rendered, so re-seed from saved config.
    sc = st.session_state.get('dq_source_config') or {}
    _restore_uc_session_state(sc)

    selected_catalog = _render_catalog_selector(api_client)
    if not selected_catalog:
        return

    selected_schema = _render_schema_selector(api_client, selected_catalog)
    if not selected_schema:
        return

    selected_table = _render_table_selector(api_client, selected_catalog, selected_schema)
    if not selected_table:
        return

    st.markdown("---")
    col1, col2 = st.columns([3, 1])
    with col1:
        st.info(f"📋 Selected: `{selected_catalog}.{selected_schema}.{selected_table}`")
    with col2:
        _handle_preview_button(api_client, selected_catalog, selected_schema, selected_table)

    _render_table_preview()
