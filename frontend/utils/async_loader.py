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
Async Data Loader for Background Prefetching

Loads data with caching to improve page load performance.
Data is cached in session state and refreshed based on TTL.
"""

import streamlit as st
from typing import Callable, Any, Optional
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)


class AsyncDataLoader:
    """Manages background data loading with caching"""
    
    @staticmethod
    def load_in_background(
        cache_key: str,
        loader_func: Callable,
        ttl_seconds: int = 300,  # 5 minutes default TTL
        force_refresh: bool = False
    ) -> Optional[Any]:
        """
        Load data with caching (synchronous - Streamlit doesn't handle threads well)
        
        Args:
            cache_key: Unique key for caching this data
            loader_func: Function to call to load the data
            ttl_seconds: Time-to-live for cached data in seconds
            force_refresh: Force refresh even if cache is valid
            
        Returns:
            Cached data if available, freshly loaded data otherwise
        """
        cache_data_key = f"_cache_{cache_key}"
        cache_timestamp_key = f"_cache_ts_{cache_key}"
        cache_loading_key = f"_cache_loading_{cache_key}"
        
        # Check if we have valid cached data
        if not force_refresh and cache_data_key in st.session_state:
            cache_timestamp = st.session_state.get(cache_timestamp_key)
            if cache_timestamp:
                age = (datetime.now() - cache_timestamp).total_seconds()
                if age < ttl_seconds:
                    # Cache is still valid
                    logging.info(f"[AsyncLoader] Cache hit for {cache_key} (age: {age:.1f}s)")
                    return st.session_state[cache_data_key]
                else:
                    logging.info(f"[AsyncLoader] Cache expired for {cache_key} (age: {age:.1f}s, TTL: {ttl_seconds}s)")
            else:
                logging.warning(f"[AsyncLoader] Cache key exists but no timestamp for {cache_key}")
        elif force_refresh:
            logging.info(f"[AsyncLoader] Force refresh requested for {cache_key}")
        else:
            logging.info(f"[AsyncLoader] No cache found for {cache_key}")
        
        # Load data synchronously (threading doesn't work reliably with Streamlit)
        try:
            logging.info(f"[AsyncLoader] Loading {cache_key} from source...")
            st.session_state[cache_loading_key] = True
            data = loader_func()
            st.session_state[cache_data_key] = data
            st.session_state[cache_timestamp_key] = datetime.now()
            st.session_state[cache_loading_key] = False
            logging.info(f"[AsyncLoader] Successfully cached {cache_key}")
            return data
        except Exception as e:
            logging.error(f"[AsyncLoader] Failed to load {cache_key}: {e}")
            st.session_state[cache_loading_key] = False
            # Return stale cache if available
            return st.session_state.get(cache_data_key)
    
    @staticmethod
    def has_valid_cache(cache_key: str, ttl_seconds: int = 300) -> bool:
        """Check if valid cached data exists without loading it"""
        cache_data_key = f"_cache_{cache_key}"
        cache_timestamp_key = f"_cache_ts_{cache_key}"
        
        if cache_data_key in st.session_state:
            cache_timestamp = st.session_state.get(cache_timestamp_key)
            if cache_timestamp:
                age = (datetime.now() - cache_timestamp).total_seconds()
                return age < ttl_seconds
        return False
    
    @staticmethod
    def is_loading(cache_key: str) -> bool:
        """Check if data is currently being loaded"""
        cache_loading_key = f"_cache_loading_{cache_key}"
        return st.session_state.get(cache_loading_key, False)
    
    @staticmethod
    def invalidate_cache(cache_key: str):
        """Clear cached data for a key"""
        cache_data_key = f"_cache_{cache_key}"
        cache_timestamp_key = f"_cache_ts_{cache_key}"
        cache_loading_key = f"_cache_loading_{cache_key}"
        
        if cache_data_key in st.session_state:
            del st.session_state[cache_data_key]
        if cache_timestamp_key in st.session_state:
            del st.session_state[cache_timestamp_key]
        if cache_loading_key in st.session_state:
            del st.session_state[cache_loading_key]
        
        logging.info(f"[AsyncLoader] Invalidated cache for {cache_key}")
    
    @staticmethod
    def cleanup_expired_cache():
        """Remove all expired cache entries to prevent memory buildup"""
        if not hasattr(st, 'session_state'):
            return
        
        expired_keys = []
        for key in list(st.session_state.keys()):
            if key.startswith('_cache_ts_'):
                cache_key = key.replace('_cache_ts_', '')
                timestamp = st.session_state.get(key)
                if timestamp:
                    age = (datetime.now() - timestamp).total_seconds()
                    # Remove if older than 1 hour (3600 seconds)
                    if age > 3600:
                        expired_keys.append(cache_key)
        
        for cache_key in expired_keys:
            AsyncDataLoader.invalidate_cache(cache_key)
        
        if expired_keys:
            logging.info(f"[AsyncLoader] Cleaned up {len(expired_keys)} expired cache entries")
    
    @staticmethod
    def prefetch_all_data(api_client, user_email: str):
        """
        Prefetch all commonly used data on app startup
        Uses simple caching instead of background threads
        
        Args:
            api_client: APIClient instance
            user_email: Current user's email
        """
        # Prefetch projects using synchronous load with caching
        try:
            AsyncDataLoader.load_in_background(
                cache_key="dq_projects",
                loader_func=lambda: api_client.get_projects(user_email),
                ttl_seconds=180  # 3 minutes for projects
            )
            logging.info(f"[AsyncLoader] Prefetched data for {user_email}")
        except Exception as e:
            logging.error(f"[AsyncLoader] Prefetch failed: {e}")


def prefetch_on_app_load():
    """
    Call this in app.py to start prefetching when user connects
    Note: With synchronous loading, this will load data immediately on first call
    """
    # Only prefetch once per session
    if 'prefetch_started' not in st.session_state:
        st.session_state.prefetch_started = True
        
        # Get API client and user
        api_client = st.session_state.get('api_client')
        user_email = st.session_state.get('current_user')
        
        if api_client and user_email:
            try:
                # Load projects immediately to cache them
                AsyncDataLoader.load_in_background(
                    cache_key="dq_projects",
                    loader_func=lambda: api_client.get_projects(user_email),
                    ttl_seconds=180  # 3 minutes for projects
                )
                logging.info("[AsyncLoader] Prefetch completed successfully")
            except Exception as e:
                logging.error(f"[AsyncLoader] Prefetch failed: {e}")
                # Don't fail silently - data will load on demand
