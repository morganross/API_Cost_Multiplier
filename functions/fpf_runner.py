"""FilePromptForge runner: invokes FilePromptForge/gpt_processor_main.py as a subprocess.

Provides:
- TEMP_BASE (reuses MA_runner.TEMP_BASE)
- async run_filepromptforge_runs(query_text: str, num_runs: int = 3, options: dict | None = None)
    -> list[(path, model_name)]
"""

from __future__ import annotations

import os
import sys
import uuid
import subprocess
import shutil
import threading
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import asyncio
import functools

# Ensure clean, non-interleaved console output across threads/processes
_PRINT_LOCK = threading.Lock()

# Optional dependency for reading YAML config (to extract model name for labeling)
try:
    import yaml  # type: ignore
except Exception:
    yaml = None  # We'll tolerate missing yaml and fall back to unknown model

# Reuse TEMP_BASE and helpers for consistency
from .MA_runner import TEMP_BASE as _PM_TEMP_BASE
from .pm_utils import ensure_temp_dir

# Public TEMP_BASE for FPF runs (alias)
TEMP_BASE = _PM_TEMP_BASE

# Paths
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, ".."))
_FPF_DIR = os.path.join(_REPO_ROOT, "FilePromptForge")
_FPF_MAIN_PATH = os.path.join(_FPF_DIR, "gpt_processor_main.py")
_FPF_DEFAULT_CONFIG = os.path.join(_FPF_DIR, "default_config.yaml")

# Defaults
_DEFAULT_PROMPT_FILES = ["standard_prompt.txt"]  # relative to FPF config's prompts_dir (default: test/prompts)


def _determine_model_from_config(config_file: Optional[str]) -> Optional[str]:
    """Parse the FilePromptForge YAML config to determine provider/model for labeling."""
    if not config_file or not os.path.exists(config_file):
        return None
    if yaml is None:
        # Cannot parse YAML; skip model detection
        return None
    try:
        with open(config_file, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        provider = (data.get("provider") or "").strip().lower()
        model: Optional[str] = None
        if provider == "openai":
            model = (data.get("openai") or {}).get("model")
        elif provider == "openrouter":
            model = (data.get("openrouter") or {}).get("model")
        elif provider == "google":
            model = (data.get("google") or {}).get("model")
        return model
    except Exception:
        return None


def _resolve_config_path(options: Optional[Dict[str, Any]]) -> str:
    """Resolve the config file path to use for FPF."""
    if options and options.get("config_file"):
        cfg = options["config_file"]
        if not os.path.isabs(cfg):
            cfg = os.path.abspath(os.path.join(_FPF_DIR, cfg))
        return cfg
    return _FPF_DEFAULT_CONFIG


def _resolve_prompt_files(options: Optional[Dict[str, Any]]) -> List[str]:
    """Resolve prompt file names to pass on CLI. These are filenames, not absolute paths."""
    if options and options.get("prompt_files"):
        # Accept list/tuple of filenames
        p = options["prompt_files"]
        if isinstance(p, (list, tuple)):
            return [str(x) for x in p if x]
        if isinstance(p, str):
            return [p]
    return list(_DEFAULT_PROMPT_FILES)


def _run_once_sync(query_text: str, run_index: int, options: Optional[Dict[str, Any]]) -> Tuple[str, Optional[str]]:
    """
    Run FilePromptForge once in a subprocess.
    Returns (absolute_path_to_output_md, model_name_or_None).
    Raises on failure.
    """
    if not os.path.exists(_FPF_MAIN_PATH):
        raise FileNotFoundError(f"FilePromptForge main not found at {_FPF_MAIN_PATH}")

    # Prepare temp run directories
    run_temp = ensure_temp_dir(os.path.join(TEMP_BASE, f"fpf_run_{uuid.uuid4()}"))
    in_dir = ensure_temp_dir(os.path.join(run_temp, "in"))
    out_dir = ensure_temp_dir(os.path.join(run_temp, "out"))

    # Write the query text to a single input markdown file
    in_file = os.path.join(in_dir, "input.md")
    with open(in_file, "w", encoding="utf-8") as fh:
        fh.write(query_text)

    # Resolve config and prompts
    config_file = _resolve_config_path(options)
    prompt_files = _resolve_prompt_files(options)
    model_override = None
    if options and options.get("model"):
        model_override = str(options["model"])

    # Build command
    # Note: gpt_processor_main.py expects '--prompt' followed by one or more filenames (nargs='+')
    cmd: List[str] = [
        sys.executable,
        "-u",
        _FPF_MAIN_PATH,
        "--config",
        config_file,
        "--input_dir",
        in_dir,
        "--output_dir",
        out_dir,
        "--log_file",
        os.path.join(run_temp, f"fpf_run_{run_index}.log"),
        "--prompt",
    ] + prompt_files

    if model_override:
        # CLI --model is only effective for some providers in FPF; pass it anyway.
        cmd += ["--model", model_override]

    # Environment
    env = os.environ.copy()
    # Force UTF-8 stdio to avoid encoding issues on Windows
    env.setdefault("PYTHONIOENCODING", "utf-8")

    # Spawn subprocess, stream stdout/stderr with prefixed lines
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        cwd=_FPF_DIR,  # run from FPF dir so relative paths in logs/config make sense
    )

    stdout_lines: List[str] = []
    stderr_lines: List[str] = []

    def _reader(stream, prefix: str, collector: List[str]) -> None:
        try:
            # Line-buffered reading to avoid interleaving partial characters
            for line in iter(stream.readline, ""):
                with _PRINT_LOCK:
                    print(f"{prefix} {line}", end="", flush=True)
                collector.append(line.rstrip("\r\n"))
        finally:
            try:
                stream.close()
            except Exception:
                pass

    t_out = threading.Thread(target=_reader, args=(process.stdout, f"[FPF run {run_index}]", stdout_lines), daemon=True)
    t_err = threading.Thread(target=_reader, args=(process.stderr, f"[FPF run {run_index} ERR]", stderr_lines), daemon=True)
    t_out.start()
    t_err.start()

    process.wait()
    t_out.join(timeout=5)
    t_err.join(timeout=5)

    if process.returncode != 0:
        stderr_out = "\n".join(stderr_lines)
        raise RuntimeError(f"FilePromptForge run failed with exit code {process.returncode}. Stderr: {stderr_out}")

    # Expected output: response_input.md in out_dir
    expected = os.path.join(out_dir, "response_input.md")
    if os.path.exists(expected):
        output_path = expected
    else:
        # Fallback: newest .md in out_dir
        md_files = sorted(Path(out_dir).glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not md_files:
            raise FileNotFoundError(f"No .md output found in {out_dir}")
        output_path = str(md_files[0].absolute())

    # Determine model name for labeling (best-effort)
    model_name: Optional[str] = model_override or _determine_model_from_config(config_file)

    return os.path.abspath(output_path), model_name


async def run_filepromptforge_runs(query_text: str, num_runs: int = 3, options: Optional[Dict[str, Any]] = None) -> List[Tuple[str, Optional[str]]]:
    """
    Run FilePromptForge num_runs times sequentially (consecutive).
    Returns a list of tuples: [(absolute_path, model_name_or_none), ...]
    """
    loop = asyncio.get_running_loop()
    successful: List[Tuple[str, Optional[str]]] = []
    for i in range(1, num_runs + 1):
        try:
            res = await loop.run_in_executor(None, functools.partial(_run_once_sync, query_text, i, options))
            successful.append(res)
        except Exception as e:
            print(f"  FPF run {i} failed: {e}")
    return successful
