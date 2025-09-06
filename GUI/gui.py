import sys
import os

# Ensure package import works when running this file directly.
# Add project root (parent of API_Cost_Multiplier) to sys.path so package imports resolve.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import the GUI launcher from the package path to preserve relative imports inside modules.
from api_cost_multiplier.GUI.functions import launch_gui


if __name__ == "__main__":
    sys.exit(launch_gui())
