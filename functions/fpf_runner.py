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
import logging

# Configure logging for fpf_runner
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "fpf_run.log")

# Configure logging for fpf_runner
logger = logging.getLogger(__name__)
# Prevent adding multiple handlers if called multiple times
if logger.hasHandlers():
    logger.handlers.clear()

logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# File handler
try:
    fh = logging.FileHandler(LOG_FILE, mode='a') # Append mode
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.info(f"Logging to file: {LOG_FILE}")
except Exception as e:
    logger.error(f"Failed to set up file handler for {LOG_FILE}: {e}")

# Console handler with UTF-8 encoding
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.DEBUG)
ch.setFormatter(formatter)
# Explicitly set encoding to utf-8 for the stream handler
ch.stream = open(ch.stream.fileno(), mode='w', encoding='utf-8', buffering=1)
logger.addHandler(ch)


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
    logger.debug(f"Determining model from config: {config_file}")
    if not config_file or not os.path.exists(config_file):
        logger.warning(f"Config file not found or not provided: {config_file}")
        return None
    if yaml is None:
        logger.warning("PyYAML not installed, cannot parse YAML config for model detection.")
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
        logger.debug(f"Detected model from config: {provider}:{model}")
        return model
    except Exception as e:
        logger.error(f"Error parsing YAML config {config_file}: {e}")
        return None


def _resolve_config_path(options: Optional[Dict[str, Any]]) -> str:
    """Resolve the config file path to use for FPF."""
    logger.debug(f"Resolving config path with options: {options}")
    if options and options.get("config_file"):
        cfg = options["config_file"]
        if not os.path.isabs(cfg):
            cfg = os.path.abspath(os.path.join(_FPF_DIR, cfg))
        logger.debug(f"Resolved config path: {cfg}")
        return cfg
    logger.debug(f"Using default config path: {_FPF_DEFAULT_CONFIG}")
    return _FPF_DEFAULT_CONFIG


def _resolve_prompt_files(options: Optional[Dict[str, Any]]) -> List[str]:
    """Resolve prompt file names to pass on CLI. These are filenames, not absolute paths."""
    logger.debug(f"Resolving prompt files with options: {options}")
    if options and options.get("prompt_files"):
        p = options["prompt_files"]
        if isinstance(p, (list, tuple)):
            resolved_files = [str(x) for x in p if x]
            logger.debug(f"Resolved prompt files: {resolved_files}")
            return resolved_files
        if isinstance(p, str):
            resolved_files = [p]
            logger.debug(f"Resolved prompt files: {resolved_files}")
            return resolved_files
    logger.debug(f"Using default prompt files: {_DEFAULT_PROMPT_FILES}")
    return list(_DEFAULT_PROMPT_FILES)


def _run_once_sync(query_text: str, run_index: int, options: Optional[Dict[str, Any]]) -> Tuple[str, Optional[str]]:
    """
    Run FilePromptForge once in a subprocess.
    Returns (absolute_path_to_output_md, model_name_or_None).
    Raises on failure.
    """
    logger.info(f"Starting FPF run {run_index}...")
    if not os.path.exists(_FPF_MAIN_PATH):
        logger.error(f"FilePromptForge main not found at {_FPF_MAIN_PATH}")
        raise FileNotFoundError(f"FilePromptForge main not found at {_FPF_MAIN_PATH}")

    # Prepare temp run directories
    run_temp = ensure_temp_dir(os.path.join(TEMP_BASE, f"fpf_run_{uuid.uuid4()}"))
    in_dir = ensure_temp_dir(os.path.join(run_temp, "in"))
    out_dir = ensure_temp_dir(os.path.join(run_temp, "out"))
    log_file_path = os.path.join(run_temp, f"fpf_run_{run_index}.log")
    logger.debug(f"Temp directories created: in={in_dir}, out={out_dir}, log={log_file_path}")

    # Write the query text to a single input markdown file
    in_file = os.path.join(in_dir, "input.md")
    try:
        with open(in_file, "w", encoding="utf-8") as fh:
            fh.write(query_text)
        logger.debug(f"Query written to input file: {in_file}")
    except Exception as e:
        logger.error(f"Failed to write query to {in_file}: {e}")
        raise

    # Resolve config and prompts
    config_file = _resolve_config_path(options)
    prompt_files = _resolve_prompt_files(options)
    model_override = None
    if options and options.get("model"):
        model_override = str(options["model"])
        logger.debug(f"Model override provided: {model_override}")

    # Build command
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
        log_file_path, # This is the log file for the subprocess
        "--prompt",
    ] + prompt_files

    if model_override:
        cmd += ["--model", model_override]

    logger.info(f"Executing FPF command: {' '.join(cmd)}")

    # Environment
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    logger.debug(f"Subprocess environment: {env.get('PYTHONIOENCODING')}")

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
            for line in iter(stream.readline, ""):
                with _PRINT_LOCK:
                    # Log to our logger as well as printing to console
                    if prefix.endswith("ERR]"):
                        logger.error(f"{prefix} {line.strip()}")
                    else:
                        logger.info(f"{prefix} {line.strip()}")
                collector.append(line.rstrip("\r\n"))
        except Exception as e:
            logger.error(f"Error reading stream for {prefix}: {e}")
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
        logger.error(f"FilePromptForge run {run_index} failed with exit code {process.returncode}. Stderr: {stderr_out}")
        raise RuntimeError(f"FilePromptForge run {run_index} failed with exit code {process.returncode}. Stderr: {stderr_out}")

    # Log captured stdout and stderr from the subprocess
    logger.debug(f"Subprocess stdout for run {run_index}:\n{chr(10).join(stdout_lines)}")
    logger.debug(f"Subprocess stderr for run {run_index}:\n{chr(10).join(stderr_lines)}")

    # Expected output: response_input.md in out_dir
    expected = os.path.join(out_dir, "response_input.md")
    if os.path.exists(expected):
        output_path = expected
    else:
        # Fallback: newest .md in out_dir
        md_files = sorted(Path(out_dir).glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not md_files:
            logger.error(f"No .md output found in {out_dir}")
            raise FileNotFoundError(f"No .md output found in {out_dir}")
        output_path = str(md_files[0].absolute())
        logger.warning(f"Using fallback output file: {output_path}")

    # Determine model name for labeling (best-effort)
    model_name: Optional[str] = model_override or _determine_model_from_config(config_file)
    logger.info(f"FPF run {run_index} completed. Output: {output_path}, Model: {model_name}")

    return os.path.abspath(output_path), model_name


async def run_filepromptforge_runs(query_text: str, num_runs: int = 3, options: Optional[Dict[str, Any]] = None) -> List[Tuple[str, Optional[str]]]:
    """
    Run FilePromptForge num_runs times sequentially (consecutive).
    Returns a list of tuples: [(absolute_path, model_name_or_none), ...]
    """
    logger.info(f"Starting {num_runs} FPF runs for query.")
    loop = asyncio.get_running_loop()
    successful: List[Tuple[str, Optional[str]]] = []
    for i in range(1, num_runs + 1):
        try:
            # Log options passed to _run_once_sync for debugging
            logger.debug(f"Calling _run_once_sync for run {i} with options: {options}")
            res = await loop.run_in_executor(None, functools.partial(_run_once_sync, query_text, i, options))
            successful.append(res)
        except Exception as e:
            logger.error(f"  FPF run {i} failed: {e}")
    logger.info(f"Successfully completed {len(successful)} out of {num_runs} FPF runs.")
    return successful
