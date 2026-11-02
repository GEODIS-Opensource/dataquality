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
Data Quality Report Dashboard Component
Displays last run report with KPIs and metrics
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Dict, Any, List


def _resolve_status_delta(status: str) -> tuple:
    """Return (delta_color, emoji) for a dataset status string."""
    if status == 'OK':
        return "normal", "✅"
    if status == 'Warning':
        return "off", "⚠️"
    return "inverse", "❌"


def _render_report_header(report_data: Dict[str, Any]) -> None:
    """Render the three-column header (project / job / last-run)."""
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Project", report_data.get('project_name', 'N/A'))
    with col2:
        st.metric("Job", report_data.get('job_name', 'N/A'))
    with col3:
        if report_data.get('execution_timestamp'):
            st.metric("Last Run", report_data['execution_timestamp'])


def _render_dataset_kpis(dataset_summary: List[Dict]) -> None:
    """Render one metric card per dataset dimension."""
    cols = st.columns(len(dataset_summary))
    for idx, dim in enumerate(dataset_summary):
        check_type = dim.get('check_type', 'Unknown')
        score = float(dim.get('dataset_score') or 0)
        status = dim.get('dataset_status', 'N/A')
        delta_color, emoji = _resolve_status_delta(status)
        with cols[idx]:
            st.metric(f"{emoji} {check_type.title()}", f"{score:.2f}%",
                      delta=status, delta_color=delta_color)


def _render_dataset_summary_table(dataset_summary: List[Dict]) -> None:
    """Render the detailed dataset-summary dataframe."""
    st.markdown("### 📈 Dataset Summary Details")
    df = pd.DataFrame(dataset_summary)
    disp_cols = ['check_type', 'dataset_score', 'dataset_status',
                 'total_columns', 'columns_ok', 'columns_warning', 'columns_ko']
    df_disp = df[disp_cols].copy()
    df_disp['dataset_score'] = pd.to_numeric(df_disp['dataset_score'], errors='coerce').fillna(0)
    for col in ['total_columns', 'columns_ok', 'columns_warning', 'columns_ko']:
        df_disp[col] = pd.to_numeric(df_disp[col], errors='coerce').fillna(0).astype(int)
    df_disp.columns = ['Check Type', 'Score (%)', 'Status', 'Total Columns', 'OK', 'Warning', 'KO']
    st.dataframe(df_disp, width="stretch", hide_index=True)


def _render_dataset_summary(dataset_summary: List[Dict]) -> None:
    """Render KPIs + detail table for the dataset summary section."""
    if not dataset_summary:
        return
    st.markdown("### 🎯 Dataset Quality Overview")
    _render_dataset_kpis(dataset_summary)
    st.markdown("---")
    _render_dataset_summary_table(dataset_summary)


def _prepare_column_df(column_summary: List[Dict]) -> pd.DataFrame:
    """Build and cast the column-summary dataframe."""
    df = pd.DataFrame(column_summary)
    for col in ['total_rows', 'valid_count', 'invalid_count', 'null_count', 'score', 'faulty_count']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df


def _render_top_failing_columns(df_filtered: pd.DataFrame) -> None:
    """Render metric cards for the top-5 failing columns."""
    failing = df_filtered[df_filtered['status'].isin(['Warning', 'KO'])].nlargest(5, 'faulty_count')
    if failing.empty:
        return
    st.markdown("#### ⚠️ Top 5 Columns with Issues")
    cols = st.columns(min(5, len(failing)))
    for idx, (_, row) in enumerate(failing.iterrows()):
        if idx < len(cols):
            emoji = "⚠️" if row['status'] == 'Warning' else "❌"
            with cols[idx]:
                st.metric(f"{emoji} {row['column_name']}",
                          f"{float(row['score'] or 0):.1f}%",
                          f"{int(row['faulty_count'] or 0)} issues")


def _highlight_status(row) -> List[str]:
    """Row-level style callback: green/yellow/red by Status."""
    colors = {'OK': '#D1FAE5', 'Warning': '#FEF3C7'}
    bg = colors.get(row['Status'], '#FEE2E2')
    return [f'background-color: {bg}'] * len(row)


def _render_column_summary_table(df_filtered: pd.DataFrame) -> None:
    """Render the styled complete column-summary dataframe."""
    st.markdown("#### 📊 Complete Column Summary")
    disp_cols = ['column_name', 'check_type', 'total_rows', 'valid_count',
                 'invalid_count', 'null_count', 'score', 'status', 'faulty_count']
    df_disp = df_filtered[disp_cols].copy()
    for col in ['total_rows', 'valid_count', 'invalid_count', 'null_count', 'faulty_count']:
        df_disp[col] = df_disp[col].astype(int)
    df_disp.columns = ['Column', 'Check Type', 'Total Rows', 'Valid',
                       'Invalid', 'Null', 'Score (%)', 'Status', 'Faulty Count']
    st.dataframe(df_disp.style.apply(_highlight_status, axis=1),
                 width="stretch", hide_index=True)


def _render_column_stats(df_filtered: pd.DataFrame) -> None:
    """Render the four summary-statistics metrics."""
    st.markdown("#### 📊 Summary Statistics")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Checks", len(df_filtered))
    with col2:
        st.metric("✅ OK", len(df_filtered[df_filtered['status'] == 'OK']))
    with col3:
        st.metric("⚠️ Warning", len(df_filtered[df_filtered['status'] == 'Warning']))
    with col4:
        st.metric("❌ KO", len(df_filtered[df_filtered['status'] == 'KO']))


def _render_column_summary(column_summary: List[Dict]) -> None:
    """Render filters, top-failing cards, table, and stats for column-level metrics."""
    if not column_summary:
        return
    st.markdown("### 📋 Column-Level Quality Metrics")
    df = _prepare_column_df(column_summary)

    col1, col2 = st.columns(2)
    with col1:
        selected_check = st.selectbox("Filter by Check Type",
                                      ['All'] + sorted(df['check_type'].unique().tolist()))
    with col2:
        selected_status = st.selectbox("Filter by Status",
                                       ['All'] + sorted(df['status'].unique().tolist()))

    df_filtered = df.copy()
    if selected_check != 'All':
        df_filtered = df_filtered[df_filtered['check_type'] == selected_check]
    if selected_status != 'All':
        df_filtered = df_filtered[df_filtered['status'] == selected_status]

    _render_top_failing_columns(df_filtered)
    _render_column_summary_table(df_filtered)
    _render_column_stats(df_filtered)


def _render_faulty_records_section(report_data: Dict[str, Any], project_id: int, api_client) -> None:
    """Render the faulty-records count and download button."""
    st.markdown("### 🔍 Faulty Records")
    faulty_count = report_data.get('faulty_records_count', 0)
    faulty_table = report_data.get('faulty_records_table', '')
    col1, col2 = st.columns([2, 1])
    with col1:
        st.metric("Total Faulty Records", f"{faulty_count:,}")
    with col2:
        if faulty_count > 0:
            if st.button("📥 Download Faulty Records (CSV)", type="primary", width="stretch"):
                with st.spinner("Preparing download..."):
                    _download_faulty_records(project_id, faulty_table, api_client)
        else:
            st.info("✅ No faulty records found!")
    if faulty_count > 0:
        st.info(f"💡 **Tip:** Faulty records are stored in table: `{faulty_table}`")


def render_report_dashboard(report_data: Dict[str, Any], project_id: int, api_client):
    """Render the data quality report dashboard."""
    st.markdown("## 📊 Last Run Report")
    _render_report_header(report_data)
    st.markdown("---")
    _render_dataset_summary(report_data.get('dataset_summary', []))
    st.markdown("---")
    _render_column_summary(report_data.get('column_summary', []))
    st.markdown("---")
    _render_faulty_records_section(report_data, project_id, api_client)


def _download_faulty_records(project_id: int, faulty_table: str, api_client):
    """Download faulty records as CSV"""
    try:
        # Use the download method (to be implemented in backend)
        csv_data = api_client.download_faulty_records(project_id, faulty_table)
        
        if csv_data:
            # Trigger download in browser
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"faulty_records_{project_id}_{timestamp}.csv"
            
            st.download_button(
                label="⬇️ Click to Download",
                data=csv_data,
                file_name=filename,
                mime="text/csv",
                width="stretch"
            )
            st.toast("Download ready!", icon="✅")
        else:
            st.error("❌ Failed to prepare download")
            
    except Exception as e:
        st.error(f"❌ Download failed: {str(e)}")


def show_report_dialog(project_id: int, project_name: str, api_client):
    """
    Show report in a dialog
    
    Args:
        project_id: Project ID
        project_name: Project name
        api_client: API client instance
    """
    @st.dialog(f"📊 Last Run Report: {project_name}", width="large")
    def display_report():
        with st.spinner("Loading report data..."):
            result = api_client.get_project_last_run_report(project_id)
            
            if result.get('status') == 'success':
                report_data = result.get('report', {})
                render_report_dashboard(report_data, project_id, api_client)
            else:
                st.error(f"❌ {result.get('message', 'Failed to load report')}")
                st.info("💡 Make sure the job has been run at least once and the result tables exist.")
        
        if st.button("Close", width="stretch", type="primary"):
            st.rerun()
    
    display_report()
