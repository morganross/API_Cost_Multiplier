import sys
import os

# Shim launcher: prefer launching via gui.py; keep this for backward compatibility.
sys.path.append(os.path.dirname(__file__))
try:
    from functions import launch_gui  # type: ignore
except Exception as e:
    raise RuntimeError(f"Failed to locate GUI launcher. Error: {e}")

if __name__ == "__main__":
    sys.exit(launch_gui())
