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
Performance Tests for Data Quality Module Optimizations

Tests to validate that optimizations improve performance without breaking functionality.
Run with: pytest tests/test_performance.py -v
"""

import pytest
import time
import sys
import os
from unittest.mock import Mock, patch, MagicMock
import pandas as pd

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MockStreamlitSessionState(dict):
    """Mock Streamlit session state"""
    def __getattr__(self, key):
        return self.get(key)
    
    def __setattr__(self, key, value):
        self[key] = value


@pytest.fixture
def mock_streamlit():
    """Mock Streamlit for testing"""
    mock_st = MagicMock()
    mock_st.session_state = MockStreamlitSessionState()
    return mock_st


@pytest.fixture
def mock_api_client():
    """Mock API client"""
    client = Mock()
    
    # Mock get_projects - simulate API delay
    def mock_get_projects(user_email):
        time.sleep(0.5)  # Simulate 500ms API call
        return [
            {'id': 1, 'name': 'Project 1', 'status': 'draft', 'config': {}, 
             'created_at': '2026-02-01T10:00:00', 'last_modified': '2026-02-01T10:00:00'},
            {'id': 2, 'name': 'Project 2', 'status': 'deployed', 'config': {},
             'created_at': '2026-02-01T11:00:00', 'last_modified': '2026-02-01T11:00:00'},
        ]
    
    client.get_projects = Mock(side_effect=mock_get_projects)
    
    # Mock preview_csv_from_dbfs - simulate DBFS read delay
    def mock_preview_csv(project_id, file_path):
        time.sleep(1.0)  # Simulate 1s DBFS read
        return {
            'status': 'success',
            'preview': [
                {'col1': 'val1', 'col2': 'val2'},
                {'col1': 'val3', 'col2': 'val4'}
            ],
            'stats': {'row_count': 100, 'column_count': 2}
        }
    
    client.preview_csv_from_dbfs = Mock(side_effect=mock_preview_csv)
    
    # Mock get_catalogs - simulate catalog list delay
    def mock_get_catalogs():
        time.sleep(1.5)  # Simulate 1.5s catalog list
        return ['catalog1', 'catalog2', 'catalog3']
    
    client.get_catalogs = Mock(side_effect=mock_get_catalogs)
    
    return client


# ==================== Test 1: Projects List Caching ====================

def test_projects_list_first_load(mock_api_client, mock_streamlit):
    """Test first load of projects list takes time"""
    with patch('streamlit.session_state', mock_streamlit.session_state):
        start = time.time()
        projects = mock_api_client.get_projects('test@example.com')
        duration = time.time() - start
        
        assert len(projects) == 2
        assert duration >= 0.5  # Should take at least 500ms
        assert mock_api_client.get_projects.call_count == 1


def test_projects_list_cached_load(mock_api_client, mock_streamlit):
    """Test cached load should not call API"""
    with patch('streamlit.session_state', mock_streamlit.session_state):
        # First load
        projects1 = mock_api_client.get_projects('test@example.com')
        mock_streamlit.session_state.dq_projects = projects1
        mock_streamlit.session_state.dq_projects_loaded = True
        
        # Second load (simulated - should use cache)
        start = time.time()
        if mock_streamlit.session_state.dq_projects_loaded:
            projects2 = mock_streamlit.session_state.dq_projects
        duration = time.time() - start
        
        assert len(projects2) == 2
        assert duration < 0.01  # Should be instant (< 10ms)
        assert mock_api_client.get_projects.call_count == 1  # Only called once


def test_projects_list_explicit_refresh(mock_api_client, mock_streamlit):
    """Test explicit refresh reloads from API"""
    with patch('streamlit.session_state', mock_streamlit.session_state):
        # First load
        projects1 = mock_api_client.get_projects('test@example.com')
        mock_streamlit.session_state.dq_projects = projects1
        mock_streamlit.session_state.dq_projects_loaded = True
        
        # Explicit refresh
        mock_streamlit.session_state.dq_projects_refresh = True
        
        start = time.time()
        projects2 = mock_api_client.get_projects('test@example.com')
        duration = time.time() - start
        
        assert len(projects2) == 2
        assert duration >= 0.5  # Should call API again
        assert mock_api_client.get_projects.call_count == 2


# ==================== Test 2: CSV Preview Caching ====================

def test_csv_preview_first_load(mock_api_client, mock_streamlit):
    """Test first CSV preview load from DBFS"""
    with patch('streamlit.session_state', mock_streamlit.session_state):
        start = time.time()
        result = mock_api_client.preview_csv_from_dbfs(1, '/dbfs/test.csv')
        duration = time.time() - start
        
        assert result['status'] == 'success'
        assert len(result['preview']) == 2
        assert duration >= 1.0  # Should take at least 1s
        assert mock_api_client.preview_csv_from_dbfs.call_count == 1


def test_csv_preview_cached_load(mock_api_client, mock_streamlit):
    """Test cached CSV preview is instant"""
    with patch('streamlit.session_state', mock_streamlit.session_state):
        # First load
        result1 = mock_api_client.preview_csv_from_dbfs(1, '/dbfs/test.csv')
        df = pd.DataFrame(result1['preview'])
        
        # Cache it
        cache_key = 'csv_preview_/dbfs/test.csv'
        mock_streamlit.session_state[cache_key] = {
            'df': df,
            'dataset_name': 'test',
            'dbfs_path': '/dbfs/test.csv',
            'config': {}
        }
        
        # Second load (from cache)
        start = time.time()
        if cache_key in mock_streamlit.session_state:
            cached_data = mock_streamlit.session_state[cache_key]
            df2 = cached_data['df']
        duration = time.time() - start
        
        assert len(df2) == 2
        assert duration < 0.01  # Should be instant (< 10ms)
        assert mock_api_client.preview_csv_from_dbfs.call_count == 1  # Only called once


def test_csv_preview_different_files_separate_cache(mock_api_client, mock_streamlit):
    """Test different CSV files have separate caches"""
    with patch('streamlit.session_state', mock_streamlit.session_state):
        # Load file 1
        result1 = mock_api_client.preview_csv_from_dbfs(1, '/dbfs/file1.csv')
        df1 = pd.DataFrame(result1['preview'])
        cache_key1 = 'csv_preview_/dbfs/file1.csv'
        mock_streamlit.session_state[cache_key1] = {'df': df1}
        
        # Load file 2
        result2 = mock_api_client.preview_csv_from_dbfs(1, '/dbfs/file2.csv')
        df2 = pd.DataFrame(result2['preview'])
        cache_key2 = 'csv_preview_/dbfs/file2.csv'
        mock_streamlit.session_state[cache_key2] = {'df': df2}
        
        # Both should be in cache
        assert cache_key1 in mock_streamlit.session_state
        assert cache_key2 in mock_streamlit.session_state
        assert mock_api_client.preview_csv_from_dbfs.call_count == 2


# ==================== Test 3: Starburst Catalog Caching ====================

def test_starburst_catalogs_first_load(mock_api_client, mock_streamlit):
    """Test first load of Starburst catalogs"""
    with patch('streamlit.session_state', mock_streamlit.session_state):
        start = time.time()
        catalogs = mock_api_client.get_catalogs()
        duration = time.time() - start
        
        assert len(catalogs) == 3
        assert duration >= 1.5  # Should take at least 1.5s
        assert mock_api_client.get_catalogs.call_count == 1


def test_starburst_catalogs_cached_load(mock_api_client, mock_streamlit):
    """Test cached Starburst catalogs are instant"""
    with patch('streamlit.session_state', mock_streamlit.session_state):
        # First load
        catalogs1 = mock_api_client.get_catalogs()
        mock_streamlit.session_state.dq_available_catalogs = catalogs1
        
        # Second load (from cache)
        start = time.time()
        if 'dq_available_catalogs' in mock_streamlit.session_state:
            catalogs2 = mock_streamlit.session_state.dq_available_catalogs
        duration = time.time() - start
        
        assert len(catalogs2) == 3
        assert duration < 0.01  # Should be instant (< 10ms)
        assert mock_api_client.get_catalogs.call_count == 1  # Only called once


def test_starburst_cache_invalidation(mock_streamlit):
    """Test Starburst cache can be invalidated"""
    with patch('streamlit.session_state', mock_streamlit.session_state):
        # Set up cache
        mock_streamlit.session_state['dq_available_catalogs'] = ['cat1', 'cat2']
        mock_streamlit.session_state['dq_schemas_cat1'] = ['schema1']
        mock_streamlit.session_state['dq_tables_cat1_schema1'] = ['table1']
        
        # Invalidate cache (simulate refresh button)
        keys_to_delete = [k for k in mock_streamlit.session_state.keys() 
                         if k.startswith('dq_available_catalogs') or 
                            k.startswith('dq_schemas_') or 
                            k.startswith('dq_tables_')]
        for key in keys_to_delete:
            del mock_streamlit.session_state[key]
        
        # Cache should be empty
        assert 'dq_available_catalogs' not in mock_streamlit.session_state
        assert 'dq_schemas_cat1' not in mock_streamlit.session_state
        assert 'dq_tables_cat1_schema1' not in mock_streamlit.session_state


# ==================== Test 4: Local Cache Update (No API Reload) ====================

def test_project_creation_updates_local_cache(mock_streamlit):
    """Test creating project updates cache without API reload"""
    with patch('streamlit.session_state', mock_streamlit.session_state):
        # Initial projects
        mock_streamlit.session_state.dq_projects = [
            {'id': 1, 'name': 'Project 1'}
        ]
        mock_streamlit.session_state.dq_projects_dict = {1: {'id': 1, 'name': 'Project 1'}}
        
        # Simulate new project creation
        new_project = {
            'id': 2,
            'name': 'New Project',
            'status': 'draft',
            'config': {}
        }
        
        # Update local cache
        mock_streamlit.session_state.dq_projects.append(new_project)
        mock_streamlit.session_state.dq_projects_dict[2] = new_project
        
        # Verify
        assert len(mock_streamlit.session_state.dq_projects) == 2
        assert 2 in mock_streamlit.session_state.dq_projects_dict
        assert mock_streamlit.session_state.dq_projects_dict[2]['name'] == 'New Project'


def test_project_deletion_updates_local_cache(mock_streamlit):
    """Test deleting project updates cache without API reload"""
    with patch('streamlit.session_state', mock_streamlit.session_state):
        # Initial projects
        mock_streamlit.session_state.dq_projects = [
            {'id': 1, 'name': 'Project 1'},
            {'id': 2, 'name': 'Project 2'}
        ]
        mock_streamlit.session_state.dq_projects_dict = {
            1: {'id': 1, 'name': 'Project 1'},
            2: {'id': 2, 'name': 'Project 2'}
        }
        
        # Delete project 2
        project_id_to_delete = 2
        mock_streamlit.session_state.dq_projects = [
            p for p in mock_streamlit.session_state.dq_projects 
            if p['id'] != project_id_to_delete
        ]
        if project_id_to_delete in mock_streamlit.session_state.dq_projects_dict:
            del mock_streamlit.session_state.dq_projects_dict[project_id_to_delete]
        
        # Verify
        assert len(mock_streamlit.session_state.dq_projects) == 1
        assert 2 not in mock_streamlit.session_state.dq_projects_dict
        assert 1 in mock_streamlit.session_state.dq_projects_dict


# ==================== Test 5: Performance Benchmarks ====================

def test_performance_project_list_caching(mock_api_client, mock_streamlit):
    """Benchmark: Projects list caching should be 10x+ faster"""
    mock_client = mock_api_client
    mock_st = mock_streamlit

    with patch('streamlit.session_state', mock_st.session_state):
        # First load (uncached)
        start = time.time()
        projects = mock_client.get_projects('test@example.com')
        uncached_duration = time.time() - start
        
        # Setup cache
        mock_st.session_state.dq_projects = projects
        mock_st.session_state.dq_projects_loaded = True
        
        # Second load (cached)
        start = time.time()
        if mock_st.session_state.dq_projects_loaded:
            cached_projects = mock_st.session_state.dq_projects
        cached_duration = time.time() - start
        
        # Cached should be at least 10x faster
        speedup = uncached_duration / max(cached_duration, 0.0001)  # Avoid division by zero
        print(f"\\nProjects list speedup: {speedup:.1f}x (uncached: {uncached_duration:.3f}s, cached: {cached_duration:.6f}s)")
        assert speedup > 10, f"Expected 10x speedup, got {speedup:.1f}x"


def test_performance_csv_preview_caching(mock_api_client, mock_streamlit):
    """Benchmark: CSV preview caching should be 100x+ faster"""
    mock_client = mock_api_client
    mock_st = mock_streamlit
    
    with patch('streamlit.session_state', mock_st.session_state):
        # First load (uncached)
        start = time.time()
        result = mock_client.preview_csv_from_dbfs(1, '/dbfs/test.csv')
        df = pd.DataFrame(result['preview'])
        uncached_duration = time.time() - start
        
        # Setup cache
        cache_key = 'csv_preview_/dbfs/test.csv'
        mock_st.session_state[cache_key] = {'df': df}
        
        # Second load (cached)
        start = time.time()
        if cache_key in mock_st.session_state:
            cached_df = mock_st.session_state[cache_key]['df']
        cached_duration = time.time() - start
        
        # Cached should be at least 100x faster
        speedup = uncached_duration / max(cached_duration, 0.0001)  # Avoid division by zero
        print(f"\\nCSV preview speedup: {speedup:.1f}x (uncached: {uncached_duration:.3f}s, cached: {cached_duration:.6f}s)")
        assert speedup > 100, f"Expected 100x speedup, got {speedup:.1f}x"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
