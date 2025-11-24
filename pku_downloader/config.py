"""
Configuration management for PKU Downloader.
"""
import configparser
from pathlib import Path
from typing import Dict, Any
import os
import sys
import platform

class Config:
    """Configuration wrapper for managing settings."""

    # Determine default browser based on platform
    @staticmethod
    def _get_default_browser():
        """Get default browser based on platform."""
        system = platform.system()
        if system == 'Windows':
            return 'edge'
        elif system == 'Darwin':  # macOS
            return 'safari'
        else:  # Linux and others
            return 'chrome'

    DEFAULTS = {
        'username': '',
        'password': '',
        'download_dir': str(Path.home() / 'Downloads' / 'PKU_Courses'), # Default to user downloads
        'browser': _get_default_browser.__func__(),
        'headless': True,
        'download_mode': 'specific',
        'course_ids': '',
        'overwrite': 'never',  # size, never, always
        'concurrent_downloads': 3,
        'timeout': 30,
        'retry_count': 3,
        'download_all_areas': False,
        'default_content_locations': '教学内容',
        'course_config_path': 'courses.json',
    }

    # Template for generating new config files
    TEMPLATE = """[Credentials]
# Your PKU Portal credentials (IAAA)
username = {username}
password = {password}

[Download]
# Where to save the files. Use absolute paths if possible.
download_dir = {download_dir}

# Download mode: 'all_current' (all courses this semester) or 'specific' (list below)
download_mode = all_current

# Comma separated course IDs (e.g., 12345, 67890) - only used if mode is 'specific'
course_ids =

# Overwrite existing files? Options: 'never', 'always', 'size' (if size differs)
overwrite = never

# Number of concurrent downloads
concurrent_downloads = 3

[Advanced]
# Browser to use: 'chrome', 'firefox', 'edge', or 'safari' (macOS only)
browser = edge

# Run browser in background (headless)? true/false
# Note: Safari does not support headless mode
headless = true

# Timeout in seconds for page loads
timeout = 30

# File to store course preferences (skip list, aliases)
course_config_path = {course_config_path}
"""
    
    def __init__(self, config_path: str = None):
        self.config = configparser.ConfigParser()
        self.config_path = self._find_config(config_path)
        
        if not self.config_path:
            raise FileNotFoundError("No config.ini found.")
            
        self.config.read(self.config_path, encoding='utf-8')
        self._validate()
    
    def _find_config(self, config_path: str = None) -> Path:
        """Find the damn config file."""
        if config_path and Path(config_path).exists():
            return Path(config_path)
            
        # Look in the obvious places
        search_paths = [
            Path.cwd() / 'config.ini',
            Path(__file__).parent.parent / 'config.ini',
            Path.home() / '.pku_downloader' / 'config.ini', # User directory
            Path.home() / '.downloader_config.ini',
        ]
        
        for path in search_paths:
            if path.exists():
                return path
                
        return None
    
    def _validate(self):
        """Make sure the config isn't completely broken."""
        username = self.get('username')
        password = self.get('password')
        
        if not username or username == 'YOUR_STUDENT_ID_HERE':
            raise ValueError("Username is missing in config.")
        if not password or password == 'YOUR_PASSWORD_HERE':
            raise ValueError("Password is missing in config.")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value. Simple as that."""
        # Try different sections in order of preference
        sections = ['Credentials', 'Download', 'Advanced', 'DEFAULT']
        
        for section in sections:
            if self.config.has_section(section) and self.config.has_option(section, key):
                return self.config.get(section, key)
        
        return self.DEFAULTS.get(key, default)
    
    def getint(self, key: str, default: int = 0) -> int:
        value = self.get(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    
    def getbool(self, key: str, default: bool = False) -> bool:
        value = self.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', 'yes', '1', 'on')
        return bool(value)