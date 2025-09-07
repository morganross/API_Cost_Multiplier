# Import/Capitalization Issue Report

## Summary

During an attempt to launch the GUI for the API_Cost_Multiplier project we hit a runtime failure:

```
ModuleNotFoundError: No module named 'api_cost_multiplier'
```

This occurred even though the repository directory exists locally as `API_Cost_Multiplier`. The immediate cause is an import path mismatch: code expects a package named `api_cost_multiplier` (lowercase) while the filesystem directory uses a different capitalization. On Windows this often goes unnoticed because the filesystem is case-insensitive; on Linux/macOS or in stricter runtime contexts the mismatch becomes a hard failure.

Impact and scope:
- The GUI will not start in environments where Python resolves imports case-sensitively (non-Windows or strict interpreter configurations).
- This is a portability and packaging bug that can appear intermittently depending on how the package is executed (direct script vs. module vs. installed package).
- It can block CI pipelines, cross-platform users, and automated deployments.

Reproduction summary:
- Clone the repository (directory named `API_Cost_Multiplier`).
- Run the GUI entrypoint with `python GUI/gui.py` or `python -m GUI.gui`.
- Python raises ModuleNotFoundError for `api_cost_multiplier`.

This document analyzes the root cause and provides a prioritized set of corrective options (short-term mitigations and long-term, permanent fixes).

## The Main Issue

- **Error Encountered:**  
  ```
  ModuleNotFoundError: No module named 'api_cost_multiplier'
  ```
- **Context:**  
  The code in `GUI/gui.py` contains the line:
  ```python
  from api_cost_multiplier.GUI.functions import launch_gui
  ```
  However, the actual directory is named `API_Cost_Multiplier` (with uppercase letters).
- **Root Cause:**  
  Python's import system is case-sensitive on most operating systems (Linux, macOS) but not on Windows. This means that code with mismatched import case may work on Windows but will fail on other platforms or in stricter environments. The mismatch between the import statement and the actual directory name led to the failure.

---

## Why Did This Happen?

- The project directory was cloned as `API_Cost_Multiplier` (matching the GitHub repo).
- The import statement in the code uses all lowercase: `api_cost_multiplier`.
- On Windows, this may work due to case-insensitive filesystems, but it is not portable or robust.
- Running as a module (`python -m ...`) did not resolve the issue because the import path still did not match the actual directory name.

---

## 10 Possible Permanent Solutions

1. **Use Only Relative Imports Within the Package**
   - Change all absolute imports like `from api_cost_multiplier.GUI.functions import ...` to relative imports like `from .functions import ...`.
   - Robust to any parent directory name or case, and works as long as the code is run as a module or package.

2. **Enforce a Consistent, Lowercase Directory Name in the Repo**
   - Rename the top-level directory to `api_cost_multiplier` (all lowercase) and update all import statements to match.
   - Add a pre-commit or CI check to reject PRs with incorrect casing.

3. **Add a Setup Script and Install as Editable Package**
   - Add a `setup.py` or `pyproject.toml` and require users to run `pip install -e .` from the project root.
   - This makes the package importable regardless of directory name or case.

4. **Add a Custom Import Hook to Normalize Case**
   - Write a custom import hook (using `sys.meta_path`) that normalizes all import requests to lowercase, so `import api_cost_multiplier` and `import API_Cost_Multiplier` both work.

5. **Document and Enforce Running as a Module**
   - Update all docs and scripts to require running with `python -m ...` from the project root, and add a runtime check that aborts if run incorrectly.

6. **Add a Launcher Script at the Project Root**
   - Provide a `run_gui.py` at the root that sets up `sys.path` and launches the GUI, abstracting away all import issues for the user.

7. **Add a Pre-Run Script to Check and Fix Directory Case**
   - Before running, check the actual directory name and rename it to the expected case if needed (on case-insensitive filesystems).

8. **Use Environment Variables to Set PYTHONPATH**
   - Require users to set `PYTHONPATH` to the project root in all run instructions and scripts, so imports always resolve regardless of directory name.

9. **Refactor to Flat Structure or Single Script**
   - Collapse the package structure so all code is in a single directory or script, eliminating the need for package imports.

10. **Add a CI Test Matrix for All OS/Case Combinations**
    - Set up automated tests on Windows, macOS, and Linux, with all possible directory name casings, to catch and reject any import errors before release.

---

## Conclusion

This incident is a straightforward symptom of inconsistent packaging/import expectations and is fully preventable. Recommended immediate and long-term actions:

Immediate (mitigation)
- Update the GUI entrypoint to use relative imports (minimal code change). This will allow direct execution and module execution to resolve internal imports reliably.
- Provide a root-level launcher script (e.g., `run_gui.py`) and clear run instructions (prefer `python -m API_Cost_Multiplier.GUI.gui` or `python -m GUI.gui` from the package root) so users run the project correctly.
- Add a short runtime check in the launcher that verifies imports and emits a clear error message explaining how to run the project or install it.

Long-term (permanent)
- Convert the project to an installable package (add `pyproject.toml`/`setup.cfg`) and recommend `pip install -e .` for development. Installed packages solve most local-path import ambiguity.
- Add CI checks that run the GUI startup in Linux and macOS runners to catch case-sensitivity problems before release.
- Enforce a repository naming/import convention (e.g., lowercase package name) and add pre-commit/CI lint rules that check import statements and package names for consistency.

Operational recommendations
- Document the chosen approach in the repository README and the developer onboarding guide.
- Add automated tests that start the GUI (or a headless smoke-test) in the CI matrix.
- If you expect non-developers to run the GUI, ship a small launcher script or binary wrapper to insulate end users from Python import and environment issues.

Implementing the immediate mitigations plus making the project installable and adding CI validation will eliminate this class of errors across environments.

---

*Report generated by Cline on 2025-09-06.*
