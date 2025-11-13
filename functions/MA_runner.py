"""
Multi-Agent runner: invokes the Multi_Agent_CLI.py script as a subprocess.

Provides:
- MA_CLI_PATH
- TEMP_BASE
- async run_multi_agent_once(query_text, output_folder, run_index) -> list[str]
- async run_multi_agent_runs(query_text, num_runs=3) -> list[(path, model_name)]
"""

from __future__ import annotations

import os
import sys
import uuid
import subprocess
import shutil
import json
import re  # Import re for JSON extraction from text
import time
from pathlib import Path
import threading
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime # Import datetime for _normalize_plan_output

from .pm_utils import ensure_temp_dir, load_env_file

# Path to the MA CLI script (assume MA_CLI is sibling to process_markdown directory)
MA_CLI_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "MA_CLI", "Multi_Agent_CLI.py"))

# Temp base dir for intermediate outputs (placed under process_markdown directory)
TEMP_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "temp_process_markdown_noeval"))
# Hard timeout for MA_CLI subprocess (seconds)
TIMEOUT_SECONDS = 600


async def run_multi_agent_once(query_text: str, output_folder: str, run_index: int, task_config: dict | None = None) -> List[str]:
    """
    Run the Multi_Agent_CLI.py as a subprocess once.
    Returns the path to the generated markdown file (absolute) on success.
    """
    if not os.path.exists(MA_CLI_PATH):
        raise FileNotFoundError(f"Multi-Agent CLI not found at {MA_CLI_PATH}")

    # Write query to a temp file (the MA CLI supports --query-file)
    tmp_query_file = os.path.join(output_folder, f"query_{uuid.uuid4()}.txt")
    with open(tmp_query_file, "w", encoding="utf-8") as f:
        f.write(query_text)

    # Create an explicit output filename so we can find it easily
    output_filename = f"ma_report_{run_index}_{uuid.uuid4()}.json"
    cmd = [
        sys.executable,
        "-u",
        MA_CLI_PATH,
        "--query-file",
        tmp_query_file,
        "--output-folder",
        output_folder,
        "--output-filename",
        output_filename,
        "--publish-markdown",
    ]
    # Strict file-based config: if provided, write per-run task_config.json and pass --task-config
    if task_config is not None:
        try:
            task_cfg_path = os.path.join(output_folder, "task_config.json")
            with open(task_cfg_path, "w", encoding="utf-8") as fh:
                json.dump(task_config, fh, indent=2)
            cmd.extend(["--task-config", task_cfg_path])
        except Exception as e:
            raise RuntimeError(f"Failed to write MA task_config.json: {e}")

    # Build environment: start from current env and merge keys from available .env files.
    env = os.environ.copy()
    try:
        # repo_root is two levels up from this file (process_markdown/functions -> process_markdown -> repo)
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        # Load env vars from repo-local gpt-researcher .env (if present)
        gptr_env_path = os.path.join(repo_root, "gpt-researcher", ".env")
        if os.path.exists(gptr_env_path):
            env.update(load_env_file(gptr_env_path))

        # Also load env vars from MA CLI .env if present (priority after gpt_researcher so explicit MA .env can override)
        try:
            ma_env_path = os.path.join(os.path.dirname(MA_CLI_PATH), ".env")
            if os.path.exists(ma_env_path):
                # Use setdefault behavior similar to original: do not overwrite existing env keys
                for k, v in load_env_file(ma_env_path).items():
                    env.setdefault(k, v)
        except Exception:
            pass

        # Ensure non-streaming is the default for MA subprocess to avoid streaming permission errors.
        # The create_chat_completion function still supports streaming if allowed, but programmatic
        # runs should not attempt streaming by default.
        env.setdefault("GPTR_DISABLE_STREAMING", "true")
        # Force Python stdout/stderr to use UTF-8 in the subprocess to avoid UnicodeEncodeError (Windows CP1252)
        env.setdefault("PYTHONIOENCODING", "utf-8")

    except Exception:
        # non-fatal; continue with existing env
        pass

    # Ensure output folder exists
    os.makedirs(output_folder, exist_ok=True)

    # Prefer repo-local gpt-researcher package so the MA CLI imports local multi_agents
    local_gpt_researcher = os.path.join(repo_root, "gpt-researcher")
    local_multi_agents = os.path.join(local_gpt_researcher, "multi_agents")

    # Ensure repo_root gpt-researcher and multi_agents are on PYTHONPATH for subprocess
    py_paths = []
    patches_dir = os.path.join(repo_root, "patches")

    if os.path.isdir(patches_dir):
        py_paths.append(patches_dir)
    if os.path.isdir(local_gpt_researcher):
        py_paths.append(local_gpt_researcher)
    if os.path.isdir(local_multi_agents): # Add local_multi_agents to PYTHONPATH
        py_paths.append(local_multi_agents)

    # Append existing PYTHONPATH from environment only if it's not already in py_paths
    existing_pythonpath = env.get("PYTHONPATH", "")
    if existing_pythonpath:
        for p in existing_pythonpath.split(os.pathsep):
            if p not in py_paths: # Avoid duplicates
                py_paths.append(p)
    
    env["PYTHONPATH"] = os.pathsep.join(py_paths)

    # Record run start time for artifact discovery
    start_ts = time.time()

    # Use Popen to stream stdout/stderr; disable stdin so CLI won't block on input()
    # Set cwd to local_multi_agents if it exists so the MA CLI resolves repo-local task.json and modules
    popen_cwd = local_multi_agents if local_multi_agents and os.path.isdir(local_multi_agents) else None

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        env=env,
        text=True,
        encoding='utf-8',
        errors='replace',
        bufsize=1,
        cwd=popen_cwd
    )

    # Read stdout and stderr concurrently using threads to avoid blocking
    stdout_lines = []
    stderr_lines = []

    def _reader(stream, prefix, collector):
        """
        Read from the subprocess stream character-by-character and forward output immediately,
        while ensuring each logical line is prefixed with the run identifier.

        This preserves live visibility (no newline buffering) and restores the per-line
        prefix like "[MA run 1] ..." at the start of each logical line.
        """
        try:
            buffer = ""
            line_started = False
            while True:
                ch = stream.read(1)
                if not ch:
                    # EOF: flush remaining buffer as a final line
                    if buffer:
                        if not line_started:
                            print(f"{prefix} ", end="", flush=True)
                        print(buffer, flush=True)
                        collector.append(buffer)
                        buffer = ""
                    break

                # If this is the first character of a logical line, print the prefix
                if not line_started:
                    print(f"{prefix} ", end="", flush=True)
                    line_started = True

                # Print character immediately so console shows live output
                print(ch, end="", flush=True)
                buffer += ch

                # If we've reached newline, treat as complete line
                if ch == "\n":
                    line = buffer.rstrip("\r\n")
                    collector.append(line)
                    buffer = ""
                    line_started = False
        finally:
            try:
                stream.close()
            except Exception:
                pass

    t_out = threading.Thread(target=_reader, args=(process.stdout, f"[MA run {run_index}]", stdout_lines), daemon=True)
    t_err = threading.Thread(target=_reader, args=(process.stderr, f"[MA run {run_index} ERR]", stderr_lines), daemon=True)

    t_out.start()
    t_err.start()

    # Wait for process to exit with timeout and ensure readers finish
    try:
        process.wait(timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        # Kill on timeout and emit a failed artifact; do not crash the pipeline
        try:
            process.kill()
        except Exception:
            pass
        # Join reader threads to drain buffers
        t_out.join(timeout=5)
        t_err.join(timeout=5)

        # Produce a .failed.json artifact alongside expected output
        failed_name = output_filename.replace(".json", ".failed.json")
        failed_path = os.path.join(output_folder, failed_name)
        try:
            tail_err = "\n".join(stderr_lines[-50:]) if stderr_lines else ""
            tail_out = "\n".join(stdout_lines[-50:]) if stdout_lines else ""
            with open(failed_path, "w", encoding="utf-8") as fh:
                json.dump({
                    "error": "MA_CLI subprocess timed out",
                    "timeout_seconds": TIMEOUT_SECONDS,
                    "stdout_tail": tail_out,
                    "stderr_tail": tail_err
                }, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return [os.path.abspath(failed_path)]

    t_out.join(timeout=5)
    t_err.join(timeout=5)

    stderr_out = "\n".join(stderr_lines)

    # Check return code
    if process.returncode != 0:
        # Produce a .failed.json artifact on non-zero exit, do not raise
        failed_name = output_filename.replace(".json", ".failed.json")
        failed_path = os.path.join(output_folder, failed_name)
        try:
            tail_err = "\n".join(stderr_lines[-50:]) if stderr_lines else ""
            tail_out = "\n".join(stdout_lines[-50:]) if stdout_lines else ""
            with open(failed_path, "w", encoding="utf-8") as fh:
                json.dump({
                    "error": "MA_CLI subprocess failed",
                    "exit_code": process.returncode,
                    "stdout_tail": tail_out,
                    "stderr_tail": tail_err
                }, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return [os.path.abspath(failed_path)]

    # Success: enumerate artifacts written by the tool without parsing content
    artifacts: List[str] = []
    allowed_exts = {".md", ".docx", ".pdf"}

    # Potential roots to search for new artifacts
    search_roots: List[str] = []
    # 1) The subprocess working dir outputs/
    try:
        if popen_cwd:
            outputs_dir = os.path.join(popen_cwd, "outputs")
            if os.path.isdir(outputs_dir):
                search_roots.append(outputs_dir)
    except Exception:
        pass
    # 2) The per-run temp/output folder we control
    try:
        if os.path.isdir(output_folder):
            search_roots.append(output_folder)
    except Exception:
        pass

    for root in search_roots:
        try:
            for r, _, files in os.walk(root):
                for fn in files:
                    p = os.path.join(r, fn)
                    ext = os.path.splitext(p)[1].lower()
                    if ext in allowed_exts:
                        try:
                            mtime = os.path.getmtime(p)
                            if mtime >= (start_ts - 1.0):
                                artifacts.append(os.path.abspath(p))
                        except Exception:
                            # If mtime lookup fails, include conservatively
                            artifacts.append(os.path.abspath(p))
        except Exception:
            # Ignore directory traversal errors
            pass

    # If nothing found, produce a minimal failed artifact to make failure visible
    if not artifacts:
        failed_name = output_filename.replace(".json", ".failed.json")
        failed_path = os.path.join(output_folder, failed_name)
        try:
            with open(failed_path, "w", encoding="utf-8") as fh:
                json.dump({
                    "error": "No artifacts discovered after MA_CLI success",
                    "searched_roots": search_roots
                }, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return [os.path.abspath(failed_path)]

    return artifacts

async def run_multi_agent_runs(query_text: str, num_runs: int = 3, model: str | None = None, max_sections: Optional[int] = 3) -> List[Tuple[str, str]]:
    """
    Strictly file-based invocation:
    - Requires an explicit model (no defaults, no env inference)
    - Generates a per-run task_config.json and passes --task-config to MA_CLI
    """
    if not model or not isinstance(model, str) or not model.strip():
        raise RuntimeError("MA model is required; no defaults or env fallbacks are allowed.")
    model_value = model.strip()

    results: List[Tuple[str, str]] = []
    for i in range(1, num_runs + 1):
        run_temp = ensure_temp_dir(os.path.join(TEMP_BASE, f"ma_run_{uuid.uuid4()}"))
        try:
            task_cfg = {
                "model": model_value,
                "publish_formats": {
                    "markdown": True,
                    "pdf": False,  # WeasyPrint issues are separate
                    "docx": False
                },
                "max_sections": max_sections,
                "include_human_feedback": False,
                "follow_guidelines": False,
                "verbose": False,
                # query is supplied via --query-file to MA_CLI
            }
            paths = await run_multi_agent_once(query_text, run_temp, i, task_config=task_cfg)
            for p in paths:
                results.append((p, model_value))
        except Exception as e:
            print(f"  MA run {i} failed: {e}")
    return results
