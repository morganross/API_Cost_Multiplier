import sys
import os
from pathlib import Path

# Add the API_Cost_Multiplier root to sys.path to resolve relative imports within the package
# Assumes main.py is in API_Cost_Multiplier/GUI
project_root = Path(__file__).resolve().parents[2] # Go up two levels from GUI
sys.path.insert(0, str(project_root))

try:
    from .functions import launch_gui
except Exception as e:
    raise RuntimeError(f"Failed to locate GUI launcher. Error: {e}")

if __name__ == "__main__":
    sys.exit(launch_gui())
