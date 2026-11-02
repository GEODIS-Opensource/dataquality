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
Configuration for frontend
"""
import os

# Backend API URL
BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:8080')

# Debug mode
DEBUG = True

# App Settings
APP_CONFIG = {
    "title": "Data Quality",
    "icon": "📊",
    "layout": "wide",
    "version": "0.1.0-beta",
    "support_email": "global-data-management@geodis.com",
}

# Pages Configuration
PAGES = {
    "overview": {
        "route": "/",
        "title": "Overview",
        "icon": "📊"
    },
    "tool": {
        "route": "/data-quality",
        "title": "Tool",
        "icon": "🔧"
    }
}

# Home Page Content
HOME_CONTENT = {
    "title": "Data Quality",
    "subtitle": "Visibility on quality health and a single entry point to run and monitor controls.",
    "hero": {
        "title": "Data Quality Tool",
        "description": "This application provides a centralized view of data quality health and a single access point to run and monitor quality controls. Use the Tool to apply checks, review outcomes, and export faulty records."
    },
    "footer": "This application focuses exclusively on Data Quality (rules, execution, monitoring, investigation, and export)."
}

# Data Quality Workflow Steps
DQ_WORKFLOW_STEPS = [
    {
        "number": "1",
        "title": "Choose Data Source",
        "description": "Select the dataset you want to analyze from your available data sources and catalog"
    },
    {
        "number": "2",
        "title": "Define Quality Checks",
        "description": "Select and configure the quality rules you want to apply: completeness, validity, consistency, and custom checks"
    },
    {
        "number": "3",
        "title": "Configure Thresholds",
        "description": "Set acceptable quality thresholds and define what constitutes a critical, warning, or acceptable result"
    },
    {
        "number": "4",
        "title": "Deploy Job",
        "description": "Create and deploy your data quality job to the execution environment with all configurations"
    },
    {
        "number": "5",
        "title": "Run or Schedule",
        "description": "Execute your quality checks immediately or set up a recurring schedule for automated monitoring"
    },
    {
        "number": "6",
        "title": "Review & Export",
        "description": "Analyze results, investigate faulty records, and export detailed reports for remediation"
    }
]

# CSS Styles
CUSTOM_CSS = """
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1E3A8A;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #64748B;
        margin-bottom: 2.5rem;
    }
    .hero-card-wrapper {
        position: relative;
        margin-bottom: 30px;
        cursor: pointer;
    }
    .hero-card {
        background: linear-gradient(135deg, #1E3A8A 0%, #3B82F6 100%);
        border-radius: 12px;
        padding: 50px;
        color: white;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
        position: relative;
        min-height: 200px;
    }
    .hero-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 8px 20px rgba(30, 58, 138, 0.4);
    }
    /* Hide only the hero navigation button using custom class */
    .hero-nav-button-hidden {
        display: none !important;
        visibility: hidden !important;
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        overflow: hidden !important;
        position: absolute !important;
    }
    .hero-nav-button-hidden button {
        display: none !important;
    }
    .hero-nav-button-hidden div {
        display: none !important;
    }
    .hero-nav-button-hidden * {
        display: none !important;
    }
    .hero-title {
        font-size: 2rem;
        font-weight: bold;
        margin-bottom: 20px;
    }
    .hero-description {
        font-size: 1.1rem;
        line-height: 1.8;
        margin-bottom: 30px;
        opacity: 0.95;
    }
    .hero-cta-text {
        position: absolute;
        bottom: 30px;
        right: 40px;
        background-color: white;
        color: #1E3A8A;
        padding: 12px 30px;
        font-size: 1rem;
        font-weight: 600;
        border-radius: 8px;
        transition: all 0.3s ease;
        display: inline-flex;
        align-items: center;
        gap: 8px;
        cursor: pointer;
    }
    .hero-cta-text:hover {
        background-color: #F0F9FF;
        transform: translateX(5px);
    }
    .cta-button {
        background-color: white;
        color: #1E3A8A;
        padding: 15px 40px;
        font-size: 1.2rem;
        font-weight: 600;
        border: none;
        border-radius: 8px;
        cursor: pointer;
        transition: all 0.3s;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }
    .cta-button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }
    /* Style the Streamlit primary button to be blue */
    .stButton > button[kind="primary"] {
        background-color: #3B82F6 !important;
        color: white !important;
        border: none !important;
        padding: 0.75rem 2.5rem !important;
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
        transition: all 0.3s ease !important;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #2563EB !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4) !important;
    }
    .timeline-container {
        max-width: 800px;
        margin: 0 auto;
        padding: 20px 0;
    }
    .timeline-connector {
        width: 4px;
        height: 40px;
        background: linear-gradient(180deg, #3B82F6 0%, #60A5FA 100%);
        margin: 0 auto;
        margin-left: 34px;
    }
    .workflow-step {
        background-color: #F8FAFC;
        border-radius: 12px;
        padding: 30px;
        border-left: 4px solid #3B82F6;
        margin-bottom: 0;
        cursor: default;
        position: relative;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    }
    .step-number {
        position: absolute;
        top: 50%;
        transform: translateY(-50%);
        left: -20px;
        background: linear-gradient(135deg, #1E3A8A 0%, #3B82F6 100%);
        color: white;
        width: 44px;
        height: 44px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        font-size: 1.2rem;
        box-shadow: 0 2px 8px rgba(30, 58, 138, 0.3);
        border: 4px solid white;
    }
    .step-title {
        font-size: 1.25rem;
        font-weight: 600;
        color: #1E3A8A;
        margin-top: 0;
        margin-bottom: 12px;
    }
    .step-description {
        font-size: 0.9rem;
        color: #64748B;
        line-height: 1.6;
    }
    .activity-item {
        background-color: #F8FAFC;
        border-radius: 8px;
        padding: 15px 20px;
        margin-bottom: 10px;
        border-left: 3px solid #CBD5E1;
        font-size: 0.95rem;
    }
    .activity-timestamp {
        color: #64748B;
        font-size: 0.85rem;
    }
    .section-title {
        font-size: 1.3rem;
        font-weight: 600;
        color: #1E3A8A;
        margin-top: 30px;
        margin-bottom: 15px;
    }
    .footer-scope {
        text-align: center;
        color: #94A3B8;
        font-size: 0.85rem;
        margin-top: 50px;
        padding-top: 30px;
        border-top: 1px solid #E2E8F0;
    }
    </style>
"""
