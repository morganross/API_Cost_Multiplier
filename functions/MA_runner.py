"""
Multi-Agent runner: invokes the Multi_Agent_CLI.py script as a subprocess.

Provides:
- MA_CLI_PATH
- TEMP_BASE
- async run_multi_agent_once(query_text, output_folder, run_index) -> str
- async run_multi_agent_runs(query_text, num_runs=3) -> list[(path, model_name)]
"""

from __future__ import annotations

import os
import sys
import uuid
import subprocess
import shutil
from pathlib import Path
import threading
from typing import List, Tuple

from process_markdown.functions.pm_utils import ensure_temp_dir, load_env_file

# Path to the MA CLI script (assume MA_CLI is sibling to process_markdown directory)
MA_CLI_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "MA_CLI", "Multi_Agent_CLI.py"))

# Temp base dir for intermediate outputs (placed under process_markdown directory)
TEMP_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "temp_process_markdown_noeval"))


async def run_multi_agent_once(query_text: str, output_folder: str, run_index: int) -> str:
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
    output_filename = f"ma_report_{run_index}_{uuid.uuid4()}.md"
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

    # Build environment: start from current env and merge keys from available .env files.
    env = os.environ.copy()
    try:
        # repo_root is two levels up from this file (process_markdown/functions -> process_markdown -> repo)
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        # If MA CLI doesn't have a local .env, attempt to copy the root .env into it
        try:
            ma_cli_dir = os.path.dirname(MA_CLI_PATH)
            ma_env_path = os.path.join(ma_cli_dir, ".env")
            root_env_path = os.path.join(repo_root, ".env")
            # If MA CLI .env is missing and root env exists, copy it to MA CLI dir
            if not os.path.exists(ma_env_path) and os.path.exists(root_env_path):
                try:
                    shutil.copy2(root_env_path, ma_env_path)
                    print(f"Copied root .env to MA CLI directory: {ma_env_path}")
                except Exception as copy_err:
                    print(f"Warning: failed to copy root .env to MA CLI directory: {copy_err}")

            # Also ensure gpt-researcher has an .env so programmatic runs see keys
            try:
                gptr_env_target = os.path.join(repo_root, "gptr-eval-process", "gpt-researcher-3.2.9", ".env")
                if not os.path.exists(gptr_env_target) and os.path.exists(root_env_path):
                    try:
                        shutil.copy2(root_env_path, gptr_env_target)
                        print(f"Copied root .env to gpt-researcher env: {gptr_env_target}")
                    except Exception as copy_err2:
                        print(f"Warning: failed to copy root .env to gpt-researcher env: {copy_err2}")
            except Exception:
                pass

        except Exception:
            pass

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
    try:
        # repo_root is two levels up from this file (process_markdown/functions -> process_markdown -> repo)
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        local_gpt_researcher = os.path.join(repo_root, "gpt-researcher")
        local_multi_agents = os.path.join(local_gpt_researcher, "multi_agents")
        if os.path.exists(local_gpt_researcher):
            env["PYTHONPATH"] = local_gpt_researcher + (os.pathsep + env.get("PYTHONPATH", "")) if env.get("PYTHONPATH") else local_gpt_researcher
    except Exception:
        local_multi_agents = None

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

    # Wait for process to exit and readers to finish
    process.wait()
    t_out.join(timeout=5)
    t_err.join(timeout=5)

    stderr_out = "\n".join(stderr_lines)

    # Check return code
    if process.returncode != 0:
        raise RuntimeError(f"Multi-Agent run failed with exit code {process.returncode}. Stderr: {stderr_out}")

    # Construct expected path
    md_path = os.path.join(output_folder, output_filename)
    if not os.path.exists(md_path):
        # MA CLI may write a slightly different name; try to find newest .md file in output_folder
        md_files = sorted(Path(output_folder).glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if md_files:
            return str(md_files[0].absolute())
        raise FileNotFoundError(f"Expected MA output {md_path} not found; no .md files in {output_folder}")

    return os.path.abspath(md_path)


async def run_multi_agent_runs(query_text: str, num_runs: int = 3) -> List[Tuple[str, str]]:
    """
    Run the MA CLI num_runs times. Each run gets its own temp output folder.
    Returns a list of tuples: [(absolute_path, model_name_used), ...]
    The MA model is resolved once before the runs using environment variables
    (STRATEGIC_LLM or MA_MODEL) and falls back to the MA default 'gpt-4o'.
    """
    results: List[Tuple[str, str]] = []

    # Resolve MA model (prefer STRATEGIC_LLM or MA_MODEL env). If value contains a provider (provider:model),
    # only keep the model part as requested.
    ma_model_raw = os.environ.get("STRATEGIC_LLM") or os.environ.get("MA_MODEL") or None
    if ma_model_raw and ":" in ma_model_raw:
        ma_model = ma_model_raw.split(":", 1)[1]
    else:
        ma_model = ma_model_raw or "gpt-4o"

    for i in range(1, num_runs + 1):
        run_temp = ensure_temp_dir(os.path.join(TEMP_BASE, f"ma_run_{uuid.uuid4()}"))
        try:
            md = await run_multi_agent_once(query_text, run_temp, i)
            results.append((md, ma_model))
        except Exception as e:
            print(f"  MA run {i} failed: {e}")
            # continue to next run (we preserve partial results)
    return results
