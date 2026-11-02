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
Data Quality Module

This module provides a comprehensive data quality assessment and monitoring system.
It follows a 4-step workflow:
1. Choose Data Source (CSV or Unity Catalog)
2. Configure Quality Controls (component-based)
3. Deploy DQ Job (with enable/disable controls)
4. Run or Schedule Job
"""

from .main import render

__all__ = ['render']
