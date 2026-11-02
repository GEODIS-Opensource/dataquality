"""
Data Quality Module - README

## Structure

The data_quality module is organized for maintainability and scalability:

```
data_quality/
├── __init__.py                 # Module exports
├── main.py                     # Main entry point and workflow coordinator
├── config.py                   # Component definitions (DQ_COMPONENTS)
├── session_state.py            # Session state management
├── components/                 # Reusable UI components
│   ├── __init__.py
│   ├── progress_indicator.py  # 4-step progress bar
│   ├── component_card.py       # Component selection cards
│   └── component_config.py     # Dynamic component configuration UI
├── steps/                      # Workflow steps
│   ├── __init__.py
│   ├── step1_choose_source.py  # Data source selection (CSV/Starburst)
│   ├── step2_configure_controls.py  # Component selection & config
│   ├── step3_deploy_job.py     # Job deployment & control toggles
│   └── step4_run_schedule.py   # Execution & scheduling
└── utils/                      # Utility functions
    ├── __init__.py
    └── column_extractor.py     # Extract controlled columns from configs
```

## Usage

From the main app, simply import and call:
```python
from data_quality import render
render()
```

## Key Features

- **Component-based**: Quality controls defined in config.py
- **Session state management**: Centralized in session_state.py
- **Modular steps**: Each workflow step in separate file
- **Reusable components**: UI components can be used across steps
- **Easy to extend**: Add new components or steps without touching existing code

## Adding a New Component

1. Add component definition to `config.py` in DQ_COMPONENTS list
2. Define parameters with types (multiselect, select, slider, etc.)
3. Component will automatically appear in step 2 selection
4. Configuration UI is generated automatically from params

## Adding a New Step

1. Create new file in `steps/` directory
2. Implement render function
3. Add import to `steps/__init__.py`
4. Add routing logic in `main.py`
5. Update progress indicator in `components/progress_indicator.py`
