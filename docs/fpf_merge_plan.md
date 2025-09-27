# Plan for Merging FilePromptForge Versions

## 1. Objective

This document outlines the steps to merge two different versions of `FilePromptForge` into a single, unified codebase. The goal is to combine the superior code structure of the version in the current project (`morganross/api_cost_multiplier`) with the more advanced "deep-research" features found in the alternative version (`C:\dev\betterday\API_Cost_Multiplier`).

The final version will have:
- The clean, refactored structure using a `helpers.py` module.
- The advanced logic for routing "deep-research" models to a specialized provider.
- Increased HTTP timeouts and unique filenames for better usability.

## 2. Source and Target Directories

- **Target Directory (Structure Source):** `morganross/api_cost_multiplier/FilePromptForge/`
- **Source Directory (Feature Source):** `C:\dev\betterday\API_Cost_Multiplier\FilePromptForge\`

## 3. Step-by-Step Implementation Plan

### Step 3.1: Overwrite `file_handler.py`

The most significant changes are in `file_handler.py`. We will replace the target version with the source version to import the new features.

1.  **Copy:** Replace the contents of `morganross/api_cost_multiplier/FilePromptForge/file_handler.py` with the contents of `C:\dev\betterday\API_Cost_Multiplier\FilePromptForge\file_handler.py`.

2.  **Modify Imports:** After copying, the import statements at the top of the new `file_handler.py` must be updated to work with the refactored code structure.

    Change this:
    ```python
    try:
        from fpf.fpf_main import compose_input, load_config, load_env_file
    except Exception:
        # fallback to top-level helpers if present
        from fpf_main import compose_input, load_config, load_env_file  # type: ignore
    ```

    To this:
    ```python
    try:
        from .helpers import compose_input, load_config, load_env_file  # preferred relative import
    except ImportError:
        from helpers import compose_input, load_config, load_env_file  # type: ignore
    ```

### Step 3.2: Verify `helpers.py`

Ensure that the `helpers.py` file exists in the target directory (`morganross/api_cost_multiplier/FilePromptForge/`) and contains the necessary helper functions (`load_config`, `compose_input`, `load_env_file`). No changes should be needed if the file is already present.

### Step 3.3: Copy the `openaidp` Provider

The feature source contains a specialized provider for "deep-research" models which is missing from the target.

1.  **Locate:** Find the `openaidp` directory within the source's `providers` directory (`C:\dev\betterday\API_Cost_Multiplier\FilePromptForge\providers\openaidp`).
2.  **Copy:** Copy the entire `openaidp` directory into the target's `providers` directory (`morganross/api_cost_multiplier/FilePromptForge/providers/`).

### Step 3.4: Verify `fpf_main.py`

No changes are needed for `fpf_main.py` as the analysis showed both versions are identical. The existing file in the target directory is already set up to import from `helpers.py` and will work correctly with the updated `file_handler.py`.

## 4. Expected Outcome

After completing these steps, the `FilePromptForge` in `morganross/api_cost_multiplier/` will be the definitive, most advanced version. It will correctly handle "deep-research" models while maintaining a clean and organized codebase.
