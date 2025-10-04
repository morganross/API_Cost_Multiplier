import sys
import os

# Ensure package import works when running this file directly.
# Add project root (parent of API_Cost_Multiplier) to sys.path so package imports resolve.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Prefer local gpt-researcher (and local multi_agents/task.json) over any site-installed package.
# Side-effect import to push local paths to the front of sys.path.
try:
    from api_cost_multiplier import run_gptr_local as _rgl  # side-effect: prefer local sources
except Exception:
    try:
        import run_gptr_local as _rgl  # fallback if executed as a script with package dir on sys.path
    except Exception:
        _rgl = None

# Import the GUI launcher from the package path to preserve relative imports inside modules.
try:
    from .functions import launch_gui
except Exception:
    # Fallbacks so this file can be executed both as a module and as a script.
    # 1) Try importing using the package folder name (e.g., API_Cost_Multiplier.GUI.functions)
    # 2) If that fails, load the functions.py file directly by path.
    import importlib
    import importlib.util

    parent_pkg = os.path.basename(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    try:
        mod = importlib.import_module(f"{parent_pkg}.GUI.functions")
        launch_gui = mod.launch_gui
    except Exception:
        file_path = os.path.join(os.path.dirname(__file__), "functions.py")
        spec = importlib.util.spec_from_file_location("api_cost_multiplier.GUI.functions", file_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        launch_gui = mod.launch_gui


if __name__ == "__main__":
    sys.exit(launch_gui())
