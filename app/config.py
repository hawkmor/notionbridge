"""
Configuration Management Module

All configuration loaded from environment variables.
No hardcoded credentials or secrets.
"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present (development mode)
# In production/Docker, env vars are set directly
env_path = os.getenv('ENV_PATH', '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)


class Config:
    """
    Centralized configuration management.
    All values loaded from environment variables.
    """
    
    # ============================================
    # Notion API Configuration (REQUIRED)
    # ============================================
    NOTION_API_KEY = os.getenv('NOTION_API_KEY', '')
    NOTION_DATABASE_ID = os.getenv('NOTION_DATABASE_ID', '')
    
    # ============================================
    # Xiaohongshu Configuration (REQUIRED)
    # ============================================
    XHS_BOARD_URL = os.getenv('XHS_BOARD_URL', '')
    USE_REAL_SCRAPER = os.getenv('USE_REAL_SCRAPER', 'true').lower() == 'true'
    
    # ============================================
    # Operational Configuration (OPTIONAL)
    # ============================================
    HEADLESS_MODE = os.getenv('HEADLESS_MODE', 'true').lower() == 'true'
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'user')
    ENV_PATH = env_path
    
    # CloakBrowser Anti-Detection Settings
    CLOAKBROWSER_HUMANIZE = os.getenv('CLOAKBROWSER_HUMANIZE', 'true').lower() == 'true'
    CLOAKBROWSER_PROFILE_DIR = os.getenv('CLOAKBROWSER_PROFILE_DIR', './browser_profile')
    
    # Standardized User-Agent (fallback, CloakBrowser handles this automatically)
    USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
    
    # ============================================
    # File Paths (with auto-initialization)
    # ============================================
    # These files will be created automatically if missing
    COOKIE_FILE = os.getenv('COOKIE_FILE', 'cookies.json')
    AUTH_STATE_FILE = os.getenv('AUTH_STATE_FILE', 'auth_state.json')
    SYNCED_IDS_FILE = os.getenv('SYNCED_IDS_FILE', 'synced_ids.json')
    
    # Media storage directories
    DOWNLOAD_VIDEO_DIR = os.getenv('DOWNLOAD_VIDEO_DIR', 'data/downloaded_videos')
    DOWNLOAD_COVER_DIR = os.getenv('DOWNLOAD_COVER_DIR', 'data/downloaded_covers')
    
    @classmethod
    def validate(cls) -> tuple[bool, list[str]]:
        """
        Validate required configuration.
        
        Returns:
            tuple: (is_valid, list_of_errors)
        """
        errors = []
        
        if not cls.NOTION_API_KEY:
            errors.append("NOTION_API_KEY is not set")
        elif not (cls.NOTION_API_KEY.startswith('secret_') or cls.NOTION_API_KEY.startswith('ntn_')):
            errors.append("NOTION_API_KEY appears invalid (should start with 'secret_' or 'ntn_')")
            
        if not cls.NOTION_DATABASE_ID:
            errors.append("NOTION_DATABASE_ID is not set")
            
        if cls.USE_REAL_SCRAPER and not cls.XHS_BOARD_URL:
            errors.append("XHS_BOARD_URL is required when USE_REAL_SCRAPER=true")
        
        return (len(errors) == 0, errors)
    
    @classmethod
    def initialize_storage(cls) -> None:
        """
        Initialize storage directories and files.
        Creates directories and empty files if they don't exist.
        Safe to call multiple times (idempotent).
        """
        # Create media directories
        for directory in [cls.DOWNLOAD_VIDEO_DIR, cls.DOWNLOAD_COVER_DIR]:
            Path(directory).mkdir(parents=True, exist_ok=True)
        
        # Initialize cookies file with empty list if missing
        if not os.path.exists(cls.COOKIE_FILE):
            with open(cls.COOKIE_FILE, 'w') as f:
                json.dump([], f)
        
        # Initialize synced_ids file with empty dict if missing
        if not os.path.exists(cls.SYNCED_IDS_FILE):
            with open(cls.SYNCED_IDS_FILE, 'w') as f:
                json.dump({'synced_ids': []}, f, indent=2)
    
    @classmethod
    def reload(cls) -> None:
        """Reload environment variables (useful for web UI config updates)"""
        load_dotenv(cls.ENV_PATH, override=True)
        # Re-read all env vars
        cls.NOTION_API_KEY = os.getenv('NOTION_API_KEY', '')
        cls.NOTION_DATABASE_ID = os.getenv('NOTION_DATABASE_ID', '')
        cls.XHS_BOARD_URL = os.getenv('XHS_BOARD_URL', '')
        cls.USE_REAL_SCRAPER = os.getenv('USE_REAL_SCRAPER', 'true').lower() == 'true'
        cls.HEADLESS_MODE = os.getenv('HEADLESS_MODE', 'true').lower() == 'true'
        cls.LOG_LEVEL = os.getenv('LOG_LEVEL', 'user')
        cls.CLOAKBROWSER_HUMANIZE = os.getenv('CLOAKBROWSER_HUMANIZE', 'true').lower() == 'true'
        cls.CLOAKBROWSER_PROFILE_DIR = os.getenv('CLOAKBROWSER_PROFILE_DIR', './browser_profile')


# Auto-initialize storage on module import
# This ensures directories and files exist even in fresh deployments
Config.initialize_storage()
