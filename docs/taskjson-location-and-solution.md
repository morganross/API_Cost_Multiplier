Task.json location: problem and recommended solution
====================================================

Summary
-------
This document explains the current behavior and problems caused by the MA CLI's task.json location, and a safe, incremental solution to make configuration robust and developer-friendly.

Current behavior (what MA CLI does today)
-----------------------------------------
- At startup the MA CLI runs open_task(), which tries to load a `task.json` file and uses it as the baseline task configuration.
- open_task() computes the path for `task.json` relative to the Python executable:
  - exe_dir = os.path.dirname(sys.executable)
  - config_dir = os.path.join(exe_dir, "config")
  - task_json_path = os.path.join(config_dir, "task.json")
- If `task.json` is present and valid JSON, it is used as the baseline config.
- If the file is missing or invalid, the CLI attempts to write a default `task.json` (DEFAULT_TASK) to that `config` directory.
- If writing fails (permission, read-only FS), the CLI falls back to using DEFAULT_TASK in memory and continues the run.

Why this can be a problem
-------------------------
1. Unexpected file location
   - `sys.executable` points at the Python interpreter binary — on many systems this maps to a system or virtualenv location outside the project.
   - Writing `config/task.json` relative to the interpreter can land the file in system directories (e.g., C:\Program Files\Python\..., /usr/bin/pythonX.Y), which is unexpected for repository configuration.

2. Permission issues
   - Writing to interpreter-owned directories often requires admin privileges. The CLI will fail to create or write `task.json`, raising warnings and falling back to in-memory defaults.

3. Surprising persistence behavior
   - If a user expects repo-local persistent config, they may be unable to find or modify the `task.json` that the CLI actually uses (it's in the interpreter's config dir).
   - This makes reproducibility and versioning of the task configuration harder.

4. Cross-user and environment confusion
   - Different users or CI runners using different interpreters will create `task.json` in different locations, causing inconsistent behavior across environments.

Design goals for a fix
----------------------
- Keep backward compatibility (if someone already relies on the interpreter-level config, the CLI should still work).
- Prefer a repo-local, predictable config location so developers can check it into the repo or manage it per-project.
- Keep the same precedence and merge semantics (DEFAULT_TASK → loaded task.json → --task-config → CLI args → env override).
- Provide clear logging so users know which task.json was loaded.
- Avoid requiring admin permissions to run typical developer workflows.

Recommended solution (safe, backward-compatible)
-----------------------------------------------
1. Preferred repo-local locations (checked first)
   - Check for repo-local config files in this order:
     a) A repo-level path: ./MA_CLI/config/task.json (i.e., process_markdown/MA_CLI/config/task.json)
     b) A repo config path: ./process_markdown/config/task.json (if you prefer central repo configs)
   - Use whichever exists (first match) as the baseline.

2. Fallback to interpreter-relative config (existing behavior)
   - If no repo-local file is found, fall back to the current exe-relative path:
     exe_dir = os.path.dirname(sys.executable)
     config_dir = os.path.join(exe_dir, "config")
     task_json_path = os.path.join(config_dir, "task.json")

3. Creation behavior
   - If none exist and we need to create a task.json, create it in the preferred repo-local location (MA_CLI/config/) when the process has write permission (it usually will).
   - Only if repo-local creation fails (unlikely in dev workflows) fall back to attempting creation under exe_dir/config; if that also fails, continue using DEFAULT_TASK in memory but log warnings.

4. Logging
   - Always log which path was loaded (or which default path was created). Example:
     "Loaded task.json from: {path}" or "No repo-local task.json found; created default task.json at: {path}"
   - If falling back to in-memory defaults, log that explicitly with guidance.

5. Keep merge & override semantics unchanged
   - After selecting the baseline task JSON (repo-local or exe-local or DEFAULT_TASK), the same deep-merge + CLI flag precedence applies.

Implementation notes (code sketch)
---------------------------------
Replace open_task() with logic like:

def open_task():
    repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))  # MA_CLI package dir
    repo_config_paths = [
        os.path.join(repo_dir, 'MA_CLI', 'config', 'task.json'),
        os.path.join(repo_dir, 'config', 'task.json'),
    ]
    # 1) prefer repo-local if present (first match)
    for p in repo_config_paths:
        if os.path.exists(p):
            return load_json_and_log(p)
    # 2) if not present, attempt to create repo-local config dir and write default there
    try:
        os.makedirs(os.path.dirname(repo_config_paths[0]), exist_ok=True)
        write_default_task(repo_config_paths[0])
        return DEFAULT_TASK
    except Exception:
        # fallback to exe-relative behavior (current)
        exe_dir = os.path.dirname(sys.executable)
        exe_config_dir = os.path.join(exe_dir, 'config')
        exe_task_json = os.path.join(exe_config_dir, 'task.json')
        if os.path.exists(exe_task_json):
            return load_json_and_log(exe_task_json)
        try:
            os.makedirs(exe_config_dir, exist_ok=True)
            write_default_task(exe_task_json)
            return DEFAULT_TASK
        except Exception:
            # can't write anywhere: return in-memory default and log
            log_warning("Could not persist task.json; running with in-memory defaults")
            return deepcopy(DEFAULT_TASK)

Migration & compatibility
-------------------------
- If the repo already contains a `process_markdown/MA_CLI/config/task.json`, the new behavior will pick that up automatically.
- Existing users relying on exe-relative config will still be supported because fallback preserves the old location.
- Add a README note in MA_CLI/README_CLI.md documenting the new preferred repo-local location and the config precedence.

Testing plan
------------
1. Unit test open_task() in three scenarios:
   - repo-local task.json exists (should load).
   - no repo-local file, create repo-local default (ensure file created).
   - repo-local creation fails (simulate permission), fallback to exe-relative location (simulate existing or create), or fallback to in-memory default.
2. Integration test: run MA_CLI with --task-config pointing to a test JSON and with CLI flags; confirm final config uses precedence rules.
3. Manual test on Windows and Unix using virtualenv Python to confirm location behavior.

Checklist (task_progress)
- [x] Create documentation file describing the problem and solution (this file).
- [ ] Implement open_task repo-local preference and fallback logic in MA_CLI (code change).
- [ ] Add unit tests for open_task behavior.
- [ ] Update MA_CLI README to document config precedence and repo-local path.
- [ ] Commit, push, and run quick smoke tests (invoke MA_CLI with a sample task.json and flags).

Next step
---------
I can implement the open_task() change now and add a small unit test and README update. This requires editing files and running a smoke test; tell me to "apply the code changes" and I will switch to Act mode and implement them.
