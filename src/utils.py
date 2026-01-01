# src/utils.py
import yaml
from pathlib import Path

def load_config():
    """Load config.yaml from the project root.
    
    Uses absolute path to ensure it works from any directory.
    """
    # Get the project root (parent of src/)
    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / 'config' / 'config.yaml'
    
    with open(config_path, 'r') as file:
        return yaml.safe_load(file)
