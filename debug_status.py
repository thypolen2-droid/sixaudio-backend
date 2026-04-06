import os
from pathlib import Path
import sys

# Add current dir to path for imports
sys.path.append(os.getcwd())

from modules.progress_tracker import ProgressTracker

def test_status():
    lib_path = Path("Library")
    print(f"Checking library at: {lib_path.absolute()}")
    print(f"Exists: {lib_path.exists()}")
    
    if lib_path.exists():
        stories = [d for d in lib_path.iterdir() if d.is_dir()]
        print(f"Found {len(stories)} directories:")
        for s in stories:
            print(f" - {s.name}")
            
        data = ProgressTracker.get_all_stories(lib_path)
        print(f"\nProgressTracker found {len(data)} stories.")
    else:
        print("Library directory not found!")

if __name__ == "__main__":
    test_status()
