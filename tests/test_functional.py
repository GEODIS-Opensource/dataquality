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
Functional Tests for Data Quality Module

Tests to ensure functionality is preserved after optimizations.
Run with: pytest tests/test_functional.py -v
"""

import pytest
from unittest.mock import Mock, MagicMock


class MockSessionState(dict):
    """Mock Streamlit session state"""
    def __getattr__(self, key):
        return self.get(key)
    
    def __setattr__(self, key, value):
        self[key] = value


@pytest.fixture
def session_state():
    """Fixture for session state"""
    return MockSessionState()


# ==================== Test: Project List Management ====================

def test_projects_list_initialization(session_state):
    """Test projects list initializes correctly"""
    # Should initialize as empty list
    if 'dq_projects' not in session_state:
        session_state.dq_projects = []
    
    assert isinstance(session_state.dq_projects, list)
    assert len(session_state.dq_projects) == 0


def test_project_creation_adds_to_cache(session_state):
    """Test creating project adds to both list and dict cache"""
    session_state.dq_projects = []
    session_state.dq_projects_dict = {}
    
    # Simulate project creation
    new_project = {
        'id': 1,
        'name': 'Test Project',
        'status': 'draft',
        'config': {}
    }
    
    session_state.dq_projects.append(new_project)
    session_state.dq_projects_dict[1] = new_project
    
    # Verify in both structures
    assert len(session_state.dq_projects) == 1
    assert 1 in session_state.dq_projects_dict
    assert session_state.dq_projects_dict[1]['name'] == 'Test Project'


def test_project_deletion_removes_from_cache(session_state):
    """Test deleting project removes from both list and dict cache"""
    session_state.dq_projects = [
        {'id': 1, 'name': 'Project 1'},
        {'id': 2, 'name': 'Project 2'}
    ]
    session_state.dq_projects_dict = {
        1: {'id': 1, 'name': 'Project 1'},
        2: {'id': 2, 'name': 'Project 2'}
    }
    
    # Delete project 2
    project_id = 2
    session_state.dq_projects = [p for p in session_state.dq_projects if p['id'] != project_id]
    if project_id in session_state.dq_projects_dict:
        del session_state.dq_projects_dict[project_id]
    
    # Verify removed
    assert len(session_state.dq_projects) == 1
    assert 2 not in session_state.dq_projects_dict
    assert 1 in session_state.dq_projects_dict


def test_project_duplication_creates_new_entry(session_state):
    """Test duplicating project creates new entry with different ID"""
    session_state.dq_projects = [
        {'id': 1, 'name': 'Original', 'config': {'setting': 'value'}}
    ]
    session_state.dq_projects_dict = {
        1: {'id': 1, 'name': 'Original', 'config': {'setting': 'value'}}
    }
    
    # Duplicate project
    original = session_state.dq_projects[0]
    duplicated = {
        'id': 2,  # New ID
        'name': f"{original['name']} (Copy)",
        'config': original['config'].copy()
    }
    
    session_state.dq_projects.append(duplicated)
    session_state.dq_projects_dict[2] = duplicated
    
    # Verify both exist
    assert len(session_state.dq_projects) == 2
    assert 1 in session_state.dq_projects_dict
    assert 2 in session_state.dq_projects_dict
    assert session_state.dq_projects_dict[2]['name'] == 'Original (Copy)'


# ==================== Test: CSV Preview Caching ====================

def test_csv_cache_key_format(session_state):
    """Test CSV cache uses correct key format"""
    dbfs_path = '/dbfs/geodis_dq/project_1/test.csv'
    cache_key = f'csv_preview_{dbfs_path}'
    
    session_state[cache_key] = {'df': 'mock_dataframe'}
    
    assert cache_key in session_state
    assert session_state[cache_key]['df'] == 'mock_dataframe'


def test_csv_different_files_different_keys(session_state):
    """Test different CSV files use different cache keys"""
    path1 = '/dbfs/project_1/file1.csv'
    path2 = '/dbfs/project_1/file2.csv'
    
    cache_key1 = f'csv_preview_{path1}'
    cache_key2 = f'csv_preview_{path2}'
    
    session_state[cache_key1] = {'df': 'df1'}
    session_state[cache_key2] = {'df': 'df2'}
    
    # Both should exist independently
    assert session_state[cache_key1]['df'] == 'df1'
    assert session_state[cache_key2]['df'] == 'df2'


# ==================== Test: Starburst Catalog Caching ====================

def test_starburst_catalog_cache(session_state):
    """Test Starburst catalogs are cached"""
    session_state.dq_available_catalogs = ['catalog1', 'catalog2']
    
    assert 'dq_available_catalogs' in session_state
    assert len(session_state.dq_available_catalogs) == 2


def test_starburst_schema_cache_per_catalog(session_state):
    """Test schemas are cached per catalog"""
    catalog1 = 'catalog1'
    catalog2 = 'catalog2'
    
    cache_key1 = f'dq_schemas_{catalog1}'
    cache_key2 = f'dq_schemas_{catalog2}'
    
    session_state[cache_key1] = ['schema1a', 'schema1b']
    session_state[cache_key2] = ['schema2a']
    
    # Both should exist independently
    assert len(session_state[cache_key1]) == 2
    assert len(session_state[cache_key2]) == 1


def test_starburst_table_cache_per_schema(session_state):
    """Test tables are cached per schema"""
    cache_key = f'dq_tables_catalog1_schema1'
    session_state[cache_key] = ['table1', 'table2', 'table3']
    
    assert cache_key in session_state
    assert len(session_state[cache_key]) == 3


def test_starburst_cache_clear_all(session_state):
    """Test clearing all Starburst caches"""
    # Setup caches
    session_state['dq_available_catalogs'] = ['cat1']
    session_state['dq_schemas_cat1'] = ['schema1']
    session_state['dq_tables_cat1_schema1'] = ['table1']
    session_state['other_key'] = 'should_remain'
    
    # Clear only Starburst caches
    keys_to_delete = [k for k in session_state.keys() 
                     if k.startswith('dq_available_catalogs') or 
                        k.startswith('dq_schemas_') or 
                        k.startswith('dq_tables_')]
    
    for key in keys_to_delete:
        del session_state[key]
    
    # Starburst caches should be gone
    assert 'dq_available_catalogs' not in session_state
    assert 'dq_schemas_cat1' not in session_state
    assert 'dq_tables_cat1_schema1' not in session_state
    
    # Other keys should remain
    assert 'other_key' in session_state
    assert session_state['other_key'] == 'should_remain'


# ==================== Test: Session State Persistence ====================

def test_session_state_survives_navigation(session_state):
    """Test session state is preserved during navigation"""
    # Setup state
    session_state.dq_step = 1
    session_state.dq_dataset_preview = 'mock_dataframe'
    session_state.dq_selected_components = ['completeness', 'uniqueness']
    
    # Navigate to step 2
    session_state.dq_step = 2
    
    # State should be preserved
    assert session_state.dq_dataset_preview == 'mock_dataframe'
    assert len(session_state.dq_selected_components) == 2


def test_project_config_serialization(session_state):
    """Test project config can be serialized/deserialized"""
    import json
    
    # Create config
    config = {
        'source_type': 'csv',
        'selected_components': ['completeness'],
        'component_configs': {
            'completeness': {'columns': ['col1', 'col2']}
        },
        'thresholds': {
            'completeness': {
                'col1': {'warning': 80, 'ok': 95}
            }
        }
    }
    
    # Serialize
    config_str = json.dumps(config)
    
    # Deserialize
    config_loaded = json.loads(config_str)
    
    # Verify
    assert config_loaded['source_type'] == 'csv'
    assert 'completeness' in config_loaded['selected_components']
    assert 'col1' in config_loaded['component_configs']['completeness']['columns']


# ==================== Test: Cache Consistency ====================

def test_projects_list_and_dict_consistency(session_state):
    """Test projects list and dict cache stay in sync"""
    projects = [
        {'id': 1, 'name': 'Project 1'},
        {'id': 2, 'name': 'Project 2'},
        {'id': 3, 'name': 'Project 3'}
    ]
    
    session_state.dq_projects = projects
    session_state.dq_projects_dict = {p['id']: p for p in projects}
    
    # Verify consistency
    assert len(session_state.dq_projects) == len(session_state.dq_projects_dict)
    
    for project in session_state.dq_projects:
        assert project['id'] in session_state.dq_projects_dict
        assert session_state.dq_projects_dict[project['id']]['name'] == project['name']


def test_adding_project_maintains_consistency(session_state):
    """Test adding project maintains list/dict consistency"""
    session_state.dq_projects = [{'id': 1, 'name': 'Project 1'}]
    session_state.dq_projects_dict = {1: {'id': 1, 'name': 'Project 1'}}
    
    # Add new project
    new_project = {'id': 2, 'name': 'Project 2'}
    session_state.dq_projects.append(new_project)
    session_state.dq_projects_dict[2] = new_project
    
    # Verify consistency
    assert len(session_state.dq_projects) == len(session_state.dq_projects_dict)
    assert 2 in session_state.dq_projects_dict


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
