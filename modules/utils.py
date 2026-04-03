import re
import os
from pathlib import Path

def sanitize_filename(name):
    """Sanitizes a string to be safe for filenames."""
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()

def clean_string(s):
    """Normalize string for comparison."""
    if not s:
        return ""
    return re.sub(r'[^a-zA-Z0-9]', '', s).lower()

def natural_sort_key(s):
    """Key for natural sorting (e.g., 1, 2, 10 instead of 1, 10, 2)."""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', str(s))]

def get_project_root():
    """Returns the absolute path to the project root."""
    return Path(__file__).parent.parent

def extract_url(text):
    """
    Extracts a URL from a string. 
    Handles cases where user accidentally pastes a command like 'python scraper.py "URL"'.
    """
    if not text:
        return ""
        
    # Search for anything starting with http/https and ending before a quote or space
    # Improved regex: allow all characters except whitespace, quotes, and standard separators
    match = re.search(r'https?://[^\s"\'\[\]\(\)]+', text)
    if match:
        url = match.group(0)
        # Clean up any trailing punctuation that might have been accidentally included
        url = re.sub(r'[\.!"\'\)\]]+$', '', url)
        return url
        
    return text.strip()
