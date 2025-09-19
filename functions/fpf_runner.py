"""FilePromptForge runner: invokes FilePromptForge/fpf_main.py as a subprocess.

Provides:
- TEMP_BASE (reuses MA_runner.TEMP_BASE)
- async run_filepromptforge_runs(file_a_path: str, file_b_path: str, num_runs: int = 1, options: dict | None = None)
    -> list[(path, model_name)]
Notes:
- This integration calls the FPF main entrypoint (no importing of FPF internals).
- It uses the new two-file contract: --file-a (instructions), --file-b (input markdown).
- Output is a .txt file written to an explicit --out path; no output_dir scanning.
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
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# File handler
try:
    fh = logging.FileHandler(LOG_FILE, mode='a')  # Append mode
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
try:
    ch.stream = open(ch.stream.fileno(), mode='w', encoding='utf-8', buffering=1)  # type: ignore[attr-defined]
except Exception:
    # Best effort; keep default stream if fileno/encoding override not available
    pass
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
# New FPF entrypoint and config
_FPF_MAIN_PATH = os.path.join(_FPF_DIR, "fpf_main.py")
_FPF_CONFIG_PATH = os.path.join(_FPF_DIR, "fpf_config.yaml")
_FPF_ENV_PATH = os.path.join(_FPF_DIR, ".env")


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
        # New schema: top-level fields
        model = data.get("model")
        provider = (data.get("provider") or "").strip().lower()
        # Backward compatible fallback if older nested schema is present
        if not model:
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
    cfg = None
    if options and options.get("config_file"):
        cfg = options["config_file"]
        if not os.path.isabs(cfg):
            cfg = os.path.abspath(os.path.join(_FPF_DIR, cfg))
    else:
        cfg = _FPF_CONFIG_PATH
    logger.debug(f"Using FPF config path: {cfg}")
    return cfg


def _resolve_env_path(options: Optional[Dict[str, Any]]) -> str:
    """Resolve the .env path for FPF (canonical is FilePromptForge/.env)."""
    # Enforce canonical .env location unless explicitly overridden
    env_path = _FPF_ENV_PATH
    logger.debug(f"Using FPF env path: {env_path}")
    return env_path


def _run_once_sync(file_a_path: str, file_b_path: str, run_index: int, options: Optional[Dict[str, Any]]) -> Tuple[str, Optional[str]]:
    """
    Run FilePromptForge once in a subprocess using the new main entrypoint contract.
    Returns (absolute_path_to_output_txt, model_name_or_None).
    Raises on failure.
    """
    logger.info(f"Starting FPF run {run_index}...")
    if not os.path.exists(_FPF_MAIN_PATH):
        logger.error(f"FilePromptForge main not found at {_FPF_MAIN_PATH}")
        raise FileNotFoundError(f"FilePromptForge main not found at {_FPF_MAIN_PATH}")

    # Validate inputs
    if not os.path.exists(file_a_path):
        raise FileNotFoundError(f"file_a not found: {file_a_path}")
    if not os.path.exists(file_b_path):
        raise FileNotFoundError(f"file_b not found: {file_b_path}")

    # Prepare temp run directories
    run_temp = ensure_temp_dir(os.path.join(TEMP_BASE, f"fpf_run_{uuid.uuid4()}"))
    out_dir = ensure_temp_dir(os.path.join(run_temp, "out"))
    log_file_path = os.path.join(run_temp, f"fpf_run_{run_index}.log")  # local runner log if needed
    logger.debug(f"Temp directories created: out={out_dir}, log={log_file_path}")

    # Resolve config and env
    config_file = _resolve_config_path(options)
    env_file = _resolve_env_path(options)

    # Optional overrides
    model_override = None
    provider_override = None
    if options and options.get("model"):
        model_override = str(options["model"])
        logger.debug(f"Model override provided: {model_override}")
    if options and options.get("provider"):
        provider_override = str(options["provider"])
        logger.debug(f"Provider override provided: {provider_override}")

    # Build explicit output path (keep .txt)
    out_file = os.path.join(out_dir, f"response_{run_index}.txt")

    # Build command
    cmd: List[str] = [
        sys.executable,
        "-u",
        _FPF_MAIN_PATH,
        "--config",
        config_file,
        "--env",
        env_file,
        "--file-a",
        file_a_path,
        "--file-b",
        file_b_path,
        "--out",
        out_file,
    ]
    if provider_override:
        cmd += ["--provider", provider_override]
    if model_override:
        cmd += ["--model", model_override]

    logger.info(f"Executing FPF command: {' '.join(cmd)}")

    # Environment
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    # Ensure the ACM repo root is on PYTHONPATH so `filepromptforge` shim is importable by fpf_main.py
    try:
        existing_pp = env.get("PYTHONPATH", "")
        parts = [p for p in existing_pp.split(os.pathsep) if p]
        if _REPO_ROOT not in parts:
            parts.insert(0, _REPO_ROOT)
        env["PYTHONPATH"] = os.pathsep.join(parts)
    except Exception:
        # Best effort: if anything fails, fall back to existing env
        pass
    logger.debug(f"Subprocess environment: {env.get('PYTHONIOENCODING')}, PYTHONPATH includes repo root={_REPO_ROOT in env.get('PYTHONPATH', '')}")

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

    # Determine output path: prefer explicit --out; fallback to path printed on stdout if present
    output_path: Optional[str] = out_file if os.path.exists(out_file) else None
    if not output_path:
        # Attempt to parse last non-empty stdout line as a path (fpf_main.py prints the path on success)
        for line in reversed(stdout_lines):
            cand = line.strip()
            if cand and (os.path.isabs(cand) or cand.endswith(".txt")):
                output_path = cand
                break

    if not output_path or not os.path.exists(output_path):
        logger.error(f"Expected output not found. --out path: {out_file}")
        raise FileNotFoundError(f"FPF run {run_index} reported success but no output file found at {out_file}")

    # Determine model name for labeling (best-effort)
    model_name: Optional[str] = model_override or _determine_model_from_config(config_file)
    logger.info(f"FPF run {run_index} completed. Output: {output_path}, Model: {model_name}")

    return os.path.abspath(output_path), model_name


async def run_filepromptforge_runs(file_a_path: str, file_b_path: str, num_runs: int = 1, options: Optional[Dict[str, Any]] = None) -> List[Tuple[str, Optional[str]]]:
    """
    Run FilePromptForge num_runs times sequentially (consecutive).
    Returns a list of tuples: [(absolute_path_to_output_txt, model_name_or_none), ...]
    """
    logger.info(f"Starting {num_runs} FPF runs for inputs. file_a={file_a_path}, file_b={file_b_path}")
    loop = asyncio.get_running_loop()
    successful: List[Tuple[str, Optional[str]]] = []
    for i in range(1, num_runs + 1):
        try:
            logger.debug(f"Calling _run_once_sync for run {i} with options: {options}")
            res = await loop.run_in_executor(None, functools.partial(_run_once_sync, file_a_path, file_b_path, i, options))
            successful.append(res)
        except Exception as e:
            logger.error(f"  FPF run {i} failed: {e}")
    logger.info(f"Successfully completed {len(successful)} out of {num_runs} FPF runs.")
    return successful
