"""FilePromptForge runner: invokes FilePromptForge/fpf_main.py as a subprocess.

Provides:
- TEMP_BASE (reuses MA_runner.TEMP_BASE)
- async run_filepromptforge_runs(file_a_path: str, file_b_path: str, num_runs: int = 1, options: dict | None = None)
    -> list[(path, model_name)]

Notes:
- This integration calls the FPF main entrypoint (no importing of FPF internals).
- It uses the new two-file contract: --file-a (instructions), --file-b (input markdown).
- Output is a .txt file written to an explicit --out path; no output_dir scanning.

Intelligent Retry System (4-Layer Architecture):
- Layer 1: Exit Code Protocol - FPF exits with codes 1-5 based on failure type
  - 0=success, 1=missing grounding, 2=missing reasoning, 3=both, 4=unknown, 5=other
- Layer 2: Fallback Detection - Scans for FAILURE-REPORT.json if exit code is 0
- Layer 3: Enhanced Retry Logic - Detects validation failures (codes 1-4), applies exponential backoff
  - Max 2 retries (3 total attempts), backoff: 1s/2s/4s
- Layer 4: Validation-Specific Prompts - Generates targeted instructions based on failure type
  - Grounding failures: emphasizes web search, citations, verification
  - Reasoning failures: emphasizes chain-of-thought, step-by-step analysis
  - Combined failures: applies both strategies with highest urgency

Exit Code Mapping:
  0 = Success (validation passed)
  1 = Validation failure: missing grounding only
  2 = Validation failure: missing reasoning only
  3 = Validation failure: missing both grounding and reasoning
  4 = Validation failure: unknown type
  5 = Other errors (network, API, etc.)

Retry behavior is automatically enabled for all validation failures with comprehensive logging.
"""

from __future__ import annotations

import os
import sys
import uuid
import subprocess
import shutil
import threading
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any, Callable
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
from . import fpf_events

# Import error classifier for intelligent retry
import sys as _sys
_FPF_DIR_FOR_IMPORT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "FilePromptForge")
if _FPF_DIR_FOR_IMPORT not in _sys.path:
    _sys.path.insert(0, _FPF_DIR_FOR_IMPORT)
try:
    from error_classifier import classify_error, get_retry_strategy, should_retry, calculate_backoff_delay, ErrorCategory
    _HAS_ERROR_CLASSIFIER = True
except ImportError as _e:
    logger.warning(f"Could not import error_classifier, falling back to basic retry: {_e}")
    _HAS_ERROR_CLASSIFIER = False

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


def _apply_json_override_to_config(base_config_path: str, json_value: bool, temp_dir: str) -> str:
    """
    Create a patched copy of the FPF YAML config with `json` set to the boolean `json_value`
    and any deprecated keys removed. Returns path to the patched file.
    """
    try:
        os.makedirs(temp_dir, exist_ok=True)
        patched_path = os.path.join(temp_dir, "fpf_config.patched.yaml")
        # Prefer YAML-based edit when PyYAML is available
        if yaml is not None:
            with open(base_config_path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            data["json"] = bool(json_value)
            # Remove deprecated keys if present
            if "allow_json_with_tools" in data:
                del data["allow_json_with_tools"]
            with open(patched_path, "w", encoding="utf-8") as fh:
                yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
        else:
            # Fallback: simple line-based replace
            with open(base_config_path, "r", encoding="utf-8") as fh:
                txt = fh.read()
            import re as _re
            if json_value:
                txt = _re.sub(r"(?mi)^\s*json:\s*.*$", "json: true", txt)
            else:
                txt = _re.sub(r"(?mi)^\s*json:\s*.*$", "json: false", txt)
            # Drop allow_json_with_tools lines
            txt = _re.sub(r"(?mi)^\s*allow_json_with_tools\s*:\s*.*\r?\n?", "", txt)
            with open(patched_path, "w", encoding="utf-8") as fh:
                fh.write(txt)
        logger.debug(f"Patched FPF config written to: {patched_path} (json={json_value})")
        return patched_path
    except Exception as e:
        logger.error(f"Failed to apply json override to config: {e}")
        # On failure, return the original config path to avoid blocking execution
        return base_config_path

def _is_google_provider(provider_override: Optional[str], config_file: Optional[str]) -> bool:
    """
    Determine if the current run targets the Google provider, using an explicit override
    first, then falling back to the config file.
    """
    prov = (provider_override or "").strip().lower() if provider_override else ""
    if prov:
        return prov == "google"
    if yaml is not None and config_file and os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            prov = (data.get("provider") or "").strip().lower()
            return prov == "google"
        except Exception:
            return False
    return False


def _build_enhanced_preamble(variant: str = "initial") -> str:
    """
    Build a short instruction preamble that explicitly requires citations and a rationale
    section. The 'retry' variant is stronger.
    """
    if variant == "retry":
        return (
            "MANDATORY REQUIREMENTS (Retry):\n"
            "- Include a 'Rationale' section summarizing your reasoning (concise; no chain-of-thought).\n"
            "- Include at least 3 citation links (URLs) in a 'References' section.\n"
            "- Ground all claims in the cited sources. Your response will be validated for citations and rationale.\n\n"
        )
    else:
        return (
            "MANDATORY REQUIREMENTS:\n"
            "- Include a brief 'Rationale' section (concise; no chain-of-thought).\n"
            "- Include at least 2 citation links (URLs) in a 'References' section.\n"
            "- Ground claims with the citations. Response will be validated for citations and rationale.\n\n"
        )


def _build_validation_enhanced_preamble(failure_type: str, attempt_number: int) -> str:
    """
    LAYER 4: Build enhanced instructions based on specific validation failure type.
    
    Args:
        failure_type: One of "grounding", "reasoning", or "both"
        attempt_number: Which retry attempt (1, 2, etc.) - increases urgency
    
    Returns:
        Enhanced preamble text to prepend to file_a content
    """
    urgency_level = ["CRITICAL", "MANDATORY", "ABSOLUTE"][min(attempt_number - 1, 2)]
    
    preamble = f"\n{'='*80}\n"
    preamble += f"{urgency_level} VALIDATION REQUIREMENTS (Retry Attempt {attempt_number})\n"
    preamble += f"{'='*80}\n\n"
    preamble += "YOUR PREVIOUS RESPONSE WAS REJECTED. You must fix the following issues:\n\n"
    
    if failure_type in ("grounding", "both"):
        preamble += "**GROUNDING REQUIREMENTS:**\n"
        preamble += "1. You MUST use Google Search tools to search the web for factual information\n"
        preamble += "2. Your response MUST include groundingMetadata with webSearchQueries\n"
        preamble += "3. Include at least 5 specific search queries you performed\n"
        preamble += "4. Cite sources using [1], [2], [3] notation in your text\n"
        preamble += "5. Include 'searchEntryPoint' with rendered search chips\n"
        preamble += "6. DO NOT claim to search the web without actually searching\n"
        preamble += "7. DO NOT return empty groundingMetadata: {}\n\n"
    
    if failure_type in ("reasoning", "both"):
        preamble += "**REASONING REQUIREMENTS:**\n"
        preamble += "1. Your response MUST include explicit reasoning/rationale\n"
        preamble += "2. Add a 'Reasoning' or 'Analysis' section explaining your thought process\n"
        preamble += "3. Show step-by-step how you arrived at each conclusion\n"
        preamble += "4. Explain why you chose specific scores or judgments\n"
        preamble += "5. Include content.parts[].text with substantial reasoning text\n"
        preamble += "6. DO NOT provide bare scores without explanation\n\n"
    
    preamble += f"**CONSEQUENCES:**\n"
    preamble += f"- This is retry attempt {attempt_number}\n"
    preamble += f"- Your response will be validated against these requirements\n"
    preamble += f"- Failure means this evaluation cannot be completed\n"
    preamble += f"- You MUST include both grounding AND reasoning to pass validation\n\n"
    preamble += f"{'='*80}\n\n"
    
    return preamble


def _ensure_enhanced_instructions_validation(
    file_a_path: str,
    run_temp: str,
    failure_type: str,
    attempt_number: int
) -> str:
    """
    LAYER 4: Create enhanced version of file_a with validation-specific requirements.
    
    Args:
        file_a_path: Original file_a path
        run_temp: Temp directory for this run
        failure_type: "grounding", "reasoning", or "both"
        attempt_number: Which retry attempt (1, 2, etc.)
    
    Returns:
        Path to enhanced file_a
    """
    try:
        with open(file_a_path, "r", encoding="utf-8") as f:
            original_content = f.read()
        
        # Build targeted enhancement
        enhanced_preamble = _build_validation_enhanced_preamble(failure_type, attempt_number)
        
        # Prepend to original content
        enhanced_content = enhanced_preamble + original_content
        
        # Write to new file
        enhanced_path = os.path.join(run_temp, f"file_a_enhanced_validation_{failure_type}_attempt{attempt_number}.txt")
        with open(enhanced_path, "w", encoding="utf-8") as f:
            f.write(enhanced_content)
        
        logger.debug(f"Created validation-enhanced file_a at {enhanced_path} ({len(enhanced_preamble)} chars added)")
        return enhanced_path
        
    except Exception as e:
        logger.error(f"Failed to create validation-enhanced file_a: {e}")
        return file_a_path  # Fallback to original


def _ensure_enhanced_instructions(base_instructions_path: str, run_temp: str, variant: str) -> str:
    """
    Write an enhanced instructions file that prepends a validation-oriented preamble
    to the original instructions. Returns the new file path.
    """
    try:
        with open(base_instructions_path, "r", encoding="utf-8") as fh:
            original = fh.read()
    except Exception as e:
        logger.warning(f"Failed to read base instructions '{base_instructions_path}': {e}")
        original = ""
    preamble = _build_enhanced_preamble(variant)
    enhanced = f"{preamble}{original}"
    out_path = os.path.join(run_temp, f"instructions.enhanced.{variant}.txt")
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(enhanced)
    except Exception as e:
        logger.warning(f"Failed to write enhanced instructions '{out_path}': {e}")
        return base_instructions_path
    return out_path


def _should_retry_for_validation(stderr_text: str) -> bool:
    """
    Determine whether a retry is warranted based on stderr content indicating
    validation failures (e.g., missing grounding/citations or reasoning/rationale).
    """
    s = (stderr_text or "").lower()
    keywords = [
        "missing grounding",
        "missing citations",
        "missing reasoning",
        "missing rationale",
        "mandatory checks",
        "validation",  # general signal
    ]
    return any(k in s for k in keywords)


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

    # Optional json boolean override: create a patched config copy for this run
    try:
        json_override = options.get("json") if options else None
        if isinstance(json_override, bool):
            config_file = _apply_json_override_to_config(config_file, bool(json_override), run_temp)
            logger.debug(f"Applied json override ({json_override}) to config: {config_file}")
    except Exception as e:
        logger.error(f"Failed to handle json override: {e}")

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

    # Compute instructions path (enhanced for Google if applicable)
    use_file_a_path = file_a_path
    try:
        if _is_google_provider(provider_override, config_file):
            use_file_a_path = _ensure_enhanced_instructions(file_a_path, run_temp, "initial")
            logger.debug(f"Applied Google enhanced preamble to instructions for run {run_index}: {use_file_a_path}")
    except Exception as e:
        logger.warning(f"Failed to apply enhanced Google preamble: {e}")

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
        use_file_a_path,
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
    # Propagate eval-scoped run grouping into FPF via environment
    try:
        rgid = (options or {}).get("run_group_id") if options else None
        if rgid:
            env["FPF_RUN_GROUP_ID"] = str(rgid)
        fpf_log_dir = (options or {}).get("fpf_log_dir") if options else None
        if fpf_log_dir:
            env["FPF_LOG_DIR"] = str(fpf_log_dir)
    except Exception:
        # Do not break if options missing or malformed
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

    # LAYER 2: Check for validation failure reports even if exit code is 0 (fallback detection)
    if process.returncode == 0:
        import time
        from pathlib import Path
        validation_log_dir = Path(_FPF_DIR) / "logs" / "validation"
        
        if validation_log_dir.exists():
            # Look for recent failure reports (last 5 seconds)
            cutoff_time = time.time() - 5
            recent_failures = []
            
            try:
                for report_file in validation_log_dir.glob("*-FAILURE-REPORT.json"):
                    if report_file.stat().st_mtime > cutoff_time:
                        recent_failures.append(report_file)
            except Exception as e:
                logger.debug(f"Failed to scan validation reports: {e}")
            
            if recent_failures:
                # Found validation failure despite exit code 0 (Layer 1 fallback)
                logger.warning(f"FPF run {run_index}: exit code 0 but found {len(recent_failures)} recent failure report(s)")
                
                try:
                    import json
                    with open(recent_failures[0], 'r', encoding='utf-8') as f:
                        failure_data = json.load(f)
                    
                    missing = failure_data.get("missing", [])
                    has_grounding = not any("grounding" in str(m).lower() for m in missing)
                    has_reasoning = not any("reasoning" in str(m).lower() for m in missing)
                    
                    # Override returncode to trigger retry logic
                    if not has_grounding and not has_reasoning:
                        process.returncode = 3
                    elif not has_grounding:
                        process.returncode = 1
                    elif not has_reasoning:
                        process.returncode = 2
                    else:
                        process.returncode = 4
                    
                    logger.info(f"FPF run {run_index}: Layer 2 detection - set returncode={process.returncode} based on failure report")
                    
                except Exception as e:
                    logger.error(f"Failed to parse failure report: {e}")

    if process.returncode != 0:
        stderr_out = "\n".join(stderr_lines)
        exc = RuntimeError(f"FilePromptForge run {run_index} failed with exit code {process.returncode}")
        
        # LAYER 3: Detect validation failures by exit code (1=grounding, 2=reasoning, 3=both)
        is_validation_failure = process.returncode in (1, 2, 3, 4)
        
        if is_validation_failure:
            # Map exit code to error category for validation failures
            validation_type_map = {
                1: "grounding",
                2: "reasoning",
                3: "both",
                4: "both",  # Unknown, treat as both
            }
            validation_failure_type = validation_type_map.get(process.returncode, "both")
            
            if _HAS_ERROR_CLASSIFIER:
                # Use error classifier for validation failures
                error_category_map = {
                    1: ErrorCategory.VALIDATION_GROUNDING,
                    2: ErrorCategory.VALIDATION_REASONING,
                    3: ErrorCategory.VALIDATION_BOTH,
                    4: ErrorCategory.VALIDATION_BOTH,
                }
                error_category = error_category_map.get(process.returncode, ErrorCategory.VALIDATION_BOTH)
                retry_strategy = get_retry_strategy(error_category)
                max_retries = retry_strategy.max_retries  # Should be 2 from error_classifier
            else:
                error_category = None
                max_retries = 2  # Fallback to 2 retries for validation failures
            
            logger.warning(
                f"FPF run {run_index}: validation failure (code {process.returncode}), "
                f"type={validation_failure_type}, max_retries={max_retries}"
            )
        else:
            # Non-validation errors: use existing classification
            if _HAS_ERROR_CLASSIFIER:
                error_category = classify_error(exc, stderr_text=stderr_out)
                retry_strategy = get_retry_strategy(error_category)
                max_retries = retry_strategy.max_retries
                logger.info(f"Error classified as {error_category.value}, max_retries={max_retries}")
            else:
                # Fallback to legacy validation-based retry
                error_category = None
                max_retries = 1 if _should_retry_for_validation(stderr_out) else 0
                logger.info(f"Using legacy retry logic, max_retries={max_retries}")
            
            validation_failure_type = None
        
        # Attempt retries based on strategy
        for attempt in range(1, max_retries + 1):
            logger.warning(f"FilePromptForge run {run_index} failed (attempt {attempt}/{max_retries}), retrying...")
            
            # Calculate backoff delay
            if is_validation_failure:
                # Exponential backoff for validation: 1s, 2s, 4s
                delay_ms = 1000 * (2 ** (attempt - 1))
                logger.info(f"Validation retry backoff: {delay_ms}ms (attempt {attempt})")
                import time
                time.sleep(delay_ms / 1000.0)
            elif _HAS_ERROR_CLASSIFIER and error_category:
                delay_ms = calculate_backoff_delay(error_category, attempt)
                if delay_ms > 0:
                    logger.info(f"Backing off {delay_ms}ms before retry attempt {attempt}")
                    import time
                    time.sleep(delay_ms / 1000.0)
            
            # Prepare retry with enhanced instructions
            use_retry_file_a = use_file_a_path
            
            if is_validation_failure and validation_failure_type:
                # LAYER 4: Use validation-specific enhancement
                try:
                    use_retry_file_a = _ensure_enhanced_instructions_validation(
                        file_a_path, run_temp, validation_failure_type, attempt
                    )
                    logger.info(f"Applied validation-enhanced prompt for {validation_failure_type} failure (attempt {attempt})")
                except Exception as e:
                    logger.warning(f"Failed to apply validation enhancement: {e}")
                    # Fallback to generic enhancement
                    try:
                        use_retry_file_a = _ensure_enhanced_instructions(file_a_path, run_temp, "retry")
                        logger.debug(f"Fallback to generic enhanced preamble (attempt {attempt})")
                    except Exception:
                        pass
            
            elif _HAS_ERROR_CLASSIFIER and error_category and retry_strategy.prompt_enhancement:
                # Use generic enhancement for other retryable errors
                try:
                    use_retry_file_a = _ensure_enhanced_instructions(file_a_path, run_temp, "retry")
                    logger.debug(f"Applied enhanced preamble for retry attempt {attempt}")
                except Exception as e:
                    logger.warning(f"Failed to apply enhanced preamble: {e}")
            
            elif not _HAS_ERROR_CLASSIFIER and _should_retry_for_validation(stderr_out):
                # Legacy prompt enhancement for validation failures
                try:
                    use_retry_file_a = _ensure_enhanced_instructions(file_a_path, run_temp, "retry")
                except Exception:
                    pass
            
            retry_out_file = os.path.join(out_dir, f"response_{run_index}_retry_{attempt}.txt")
            cmd_retry: List[str] = [
                sys.executable,
                "-u",
                _FPF_MAIN_PATH,
                "--config",
                config_file,
                "--env",
                env_file,
                "--file-a",
                use_retry_file_a,
                "--file-b",
                file_b_path,
                "--out",
                retry_out_file,
            ]
            if provider_override:
                cmd_retry += ["--provider", provider_override]
            if model_override:
                cmd_retry += ["--model", model_override]

            logger.info(f"Executing FPF RETRY command (attempt {attempt}/{max_retries}): {' '.join(cmd_retry)}")

            process = subprocess.Popen(
                cmd_retry,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=_FPF_DIR,
            )

            stdout_lines_retry: List[str] = []
            stderr_lines_retry: List[str] = []

            t_out_retry = threading.Thread(target=_reader, args=(process.stdout, f"[FPF run {run_index} RETRY {attempt}]", stdout_lines_retry), daemon=True)
            t_err_retry = threading.Thread(target=_reader, args=(process.stderr, f"[FPF run {run_index} RETRY {attempt} ERR]", stderr_lines_retry), daemon=True)
            t_out_retry.start()
            t_err_retry.start()

            process.wait()
            t_out_retry.join(timeout=5)
            t_err_retry.join(timeout=5)

            if process.returncode == 0:
                # Success on retry
                stdout_lines = stdout_lines_retry
                stderr_lines = stderr_lines_retry
                out_file = retry_out_file
                logger.info(f"FPF run {run_index} retry attempt {attempt} succeeded.")
                break  # Exit retry loop on success
            else:
                stderr_retry = "\n".join(stderr_lines_retry)
                logger.error(f"FilePromptForge run {run_index} retry attempt {attempt}/{max_retries} failed with exit code {process.returncode}. Stderr: {stderr_retry}")
                
                # If this was the last retry, raise the error
                if attempt >= max_retries:
                    raise RuntimeError(f"FilePromptForge run {run_index} failed after {max_retries} retries. Original stderr: {stderr_out}\nFinal retry stderr: {stderr_retry}")
        else:
            # No retries attempted (max_retries was 0)
            logger.error(f"FilePromptForge run {run_index} failed with exit code {process.returncode}. Stderr: {stderr_out}")
            if _HAS_ERROR_CLASSIFIER and error_category:
                logger.error(f"Error category {error_category.value} does not allow retries.")
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


async def run_filepromptforge_batch(runs: List[Dict[str, Any]], options: Optional[Dict[str, Any]] = None, on_event: Optional[Callable[[Dict[str, Any]], None]] = None, timeout: Optional[float] = None) -> List[Tuple[str, Optional[str]]]:
    """
    Run FilePromptForge once in batch mode by passing a JSON array of runs via stdin.

    Each run item should include:
      - id: str
      - provider: str
      - model: str
      - file_a: str (instructions file)
      - file_b: str (input markdown file)
      - out: Optional[str]
      - overrides: Optional[dict] (e.g., {"reasoning_effort": "high", "max_completion_tokens": 50000})

    Returns a list of (output_path, model_name) for successful runs only.
    """
    import json

    # Resolve config and env the same way as single-run helper
    config_file = _resolve_config_path(options)
    env_file = _resolve_env_path(options)

    # Optional json boolean override for batch: patch config into a temp dir
    try:
        batch_temp = ensure_temp_dir(os.path.join(TEMP_BASE, f"fpf_batch_{uuid.uuid4()}"))
        json_override = options.get("json") if options else None
        if isinstance(json_override, bool):
            config_file = _apply_json_override_to_config(config_file, bool(json_override), batch_temp)
            logger.debug(f"(batch) Applied json override ({json_override}) to config: {config_file}")
    except Exception as e:
        logger.error(f"(batch) Failed to handle json override: {e}")

    # Build command for stdin-driven batch execution
    cmd: List[str] = [
        sys.executable,
        "-u",
        _FPF_MAIN_PATH,
        "--config",
        config_file,
        "--env",
        env_file,
        "--runs-stdin",
        "--batch-output",
        "json",
    ]
    # Optional CLI override of max concurrency
    if options and options.get("max_concurrency") is not None:
        try:
            cmd += ["--max-concurrency", str(int(options.get("max_concurrency")))]
        except Exception:
            pass

    logger.info("Executing FPF batch (stdin) with %d run(s)", len(runs))
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    # Ensure repo root on PYTHONPATH so imports inside FPF resolve
    try:
        existing_pp = env.get("PYTHONPATH", "")
        parts = [p for p in existing_pp.split(os.pathsep) if p]
        if _REPO_ROOT not in parts:
            parts.insert(0, _REPO_ROOT)
        env["PYTHONPATH"] = os.pathsep.join(parts)
    except Exception:
        pass
    # Propagate eval-scoped run grouping into FPF via environment
    try:
        rgid = (options or {}).get("run_group_id") if options else None
        if rgid:
            env["FPF_RUN_GROUP_ID"] = str(rgid)
        fpf_log_dir = (options or {}).get("fpf_log_dir") if options else None
        if fpf_log_dir:
            env["FPF_LOG_DIR"] = str(fpf_log_dir)
    except Exception:
        pass

    # Spawn subprocess; send runs JSON via stdin; capture stdout for results
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=_FPF_DIR,
        )
    except Exception as e:
        logger.error("Failed to spawn FPF batch process: %s", e)
        raise

    payload = json.dumps(runs, ensure_ascii=False)

    # Stream stdout/stderr in real time while sending stdin payload
    stdout_lines: List[str] = []
    stderr_lines: List[str] = []

    def _reader(stream, prefix: str, collector: List[str]) -> None:
        try:
            for line in iter(stream.readline, ""):
                with _PRINT_LOCK:
                    if prefix.endswith("ERR]"):
                        logger.error(f"{prefix} {line.strip()}")
                    else:
                        logger.info(f"{prefix} {line.strip()}")
                collector.append(line.rstrip("\r\n"))
                # Forward parsed FPF events to orchestrator (best-effort)
                try:
                    if on_event:
                        import re
                        FPF_RUN_START = re.compile(r"\[FPF RUN_START\]\s+id=(\S+)\s+kind=(\S+)\s+provider=(\S+)\s+model=(\S+)")
                        # Path may contain spaces, so capture everything until error= or end of line
                        FPF_RUN_COMPLETE = re.compile(r"\[FPF RUN_COMPLETE\]\s+id=(\S+)\s+kind=(\S+)\s+provider=(\S+)\s+model=(\S+)\s+ok=(true|false)\s+elapsed=\S+\s+status=\S+\s+path=(.+?)(?:\s+error=|$)")

                        m_start = FPF_RUN_START.search(line)
                        if m_start:
                            evt = {
                                "type": "run_start",
                                "data": {
                                    "id": m_start.group(1),
                                    "kind": m_start.group(2),
                                    "provider": m_start.group(3),
                                    "model": m_start.group(4),
                                }
                            }
                            on_event(evt)

                        m_complete = FPF_RUN_COMPLETE.search(line)
                        if m_complete:
                            path_val = m_complete.group(6) if len(m_complete.groups()) >= 6 else None
                            evt = {
                                "type": "run_complete",
                                "data": {
                                    "id": m_complete.group(1),
                                    "kind": m_complete.group(2),
                                    "provider": m_complete.group(3),
                                    "model": m_complete.group(4),
                                    "ok": m_complete.group(5).lower() == 'true',
                                    "path": path_val if path_val and path_val != "na" else None,
                                }
                            }
                            on_event(evt)
                except Exception:
                    # Do not let event parsing failures disrupt the run
                    pass
        except Exception as e:
            logger.error(f"Error reading stream for {prefix}: {e}")
        finally:
            try:
                stream.close()
            except Exception:
                pass

    # Start readers
    t_out = threading.Thread(target=_reader, args=(proc.stdout, "[FPF batch]", stdout_lines), daemon=True)
    t_err = threading.Thread(target=_reader, args=(proc.stderr, "[FPF batch ERR]", stderr_lines), daemon=True)
    t_out.start()
    t_err.start()

    # Send stdin payload and close stdin to signal EOF
    try:
        if proc.stdin:
            proc.stdin.write(payload)
            proc.stdin.flush()
            proc.stdin.close()
    except Exception as e:
        logger.error("Failed to write runs JSON to FPF stdin: %s", e)
        try:
            proc.kill()
        except Exception:
            pass
        raise

    # Wait for process to exit and join readers (do not block the asyncio event loop)
    loop = asyncio.get_running_loop()
    if timeout:
        try:
            await asyncio.wait_for(loop.run_in_executor(None, proc.wait), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error(f"FPF batch timed out after {timeout} seconds. Killing process.")
            try:
                proc.kill()
            except Exception:
                pass
            raise
    else:
        await loop.run_in_executor(None, proc.wait)
    t_out.join(timeout=5)
    t_err.join(timeout=5)

    stdout_text = "\n".join(stdout_lines)
    stderr_text = "\n".join(stderr_lines)

    if proc.returncode != 0:
        # Include some stderr in error for debugging
        snippet = (stderr_text or "").strip()
        logger.error("FPF batch failed (rc=%s). Stderr: %s", proc.returncode, snippet)
        raise RuntimeError(f"FPF batch failed (rc={proc.returncode}). {snippet}")

    # Parse JSON array from stdout; tolerate stray log lines by scanning for a JSON array
    results: List[Dict[str, Any]] = []
    parsed = False
    if stdout_text:
        # Try direct parse first
        try:
            maybe = json.loads(stdout_text.strip())
            if isinstance(maybe, list):
                results = maybe
                parsed = True
        except Exception:
            pass
        if not parsed:
            # Fallback: try to find a JSON array on a single line
            for line in reversed(stdout_text.splitlines()):
                s = line.strip()
                if s.startswith("[") and s.endswith("]"):
                    try:
                        maybe = json.loads(s)
                        if isinstance(maybe, list):
                            results = maybe
                            parsed = True
                            break
                    except Exception:
                        continue
    if not parsed:
        logger.error("Failed to parse FPF batch JSON results. Raw stdout:\n%s", stdout_text)
        raise RuntimeError("Failed to parse FPF batch JSON results from stdout")

    # Convert successful results to (path, model) tuples
    successful: List[Tuple[str, Optional[str]]] = []
    for r in results:
        try:
            p = r.get("path")
            m = r.get("model")
            if p and os.path.exists(p):
                successful.append((os.path.abspath(p), m))
        except Exception:
            continue

    logger.info("FPF batch completed. %d/%d run(s) succeeded.", len(successful), len(runs))
    return successful
