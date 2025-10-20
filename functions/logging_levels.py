"""
functions.logging_levels

Shared utilities for resolving normalized verbosity levels (Low/Medium/High)
into concrete console/file logging levels, building the named 'acm' logger
with appropriate handlers, and emitting a one-line health banner.

This module intentionally avoids calling logging.basicConfig() to prevent
global side effects and handler duplication.
"""

from __future__ import annotations

import os
import logging
from logging.handlers import RotatingFileHandler
from typing import Tuple


# Normalized level mapping
# Low    -> console WARNING (errors + basic events), file INFO (milestones)
# Medium -> console INFO, file INFO
# High   -> console DEBUG, file DEBUG
_LEVELS = {
    "low":    {"console": logging.WARNING, "file": logging.INFO},
    "medium": {"console": logging.INFO,    "file": logging.INFO},
    "high":   {"console": logging.DEBUG,   "file": logging.DEBUG},
}

_NORMALIZED_NAMES = {"low": "Low", "medium": "Medium", "high": "High"}


def _name_or_int(value: str | int | None, default: int) -> int:
    """
    Accepts a level name (Low/Medium/High) or a numeric string/int.
    Returns a logging level int, falling back to 'default' on errors.
    """
    if value is None:
        return default
    if isinstance(value, int):
        return value
    s = str(value).strip()
    # Numeric override
    if s.isdigit():
        try:
            v = int(s)
            return v
        except Exception:
            return default
    # Named mapping
    s_lower = s.lower()
    if s_lower in _LEVELS:
        return _LEVELS[s_lower]["console"] if default == logging.WARNING else _LEVELS[s_lower]["file"]
    # Also accept canonical logging names
    try:
        return logging.getLevelName(s_upper := s.upper()) if isinstance(logging.getLevelName(s.upper()), int) else default
    except Exception:
        return default


def resolve_levels(cfg: dict, component: str = "acm", env_prefix: str | None = None) -> Tuple[str, str, int, int]:
    """
    Resolve effective console/file levels for a component using precedence:
      1) Environment variables: {PREFIX}_CONSOLE_LEVEL, {PREFIX}_FILE_LEVEL
         - Default PREFIX is the uppercased component name (e.g., ACM, EVAL, MA)
      2) Config file: <component>.log.console_level, <component>.log.file_level
      3) Defaults: Low (console) / Medium (file)

    Returns: (console_name, file_name, console_level_int, file_level_int)
    Where console_name/file_name are normalized 'Low'|'Medium'|'High' (best effort).
    """
    # Defaults
    default_console_name = "Low"
    default_file_name = "Medium"

    comp_name = (component or "acm")
    comp_lower = str(comp_name).lower()
    prefix = (env_prefix or comp_lower.upper())

    # Config-sourced names for the component (e.g., acm.log.*, eval.log.*)
    cfg_comp = (cfg or {}).get(comp_lower) or {}
    cfg_log = (cfg_comp.get("log") or {}) if isinstance(cfg_comp, dict) else {}
    cfg_console = cfg_log.get("console_level", default_console_name)
    cfg_file = cfg_log.get("file_level", default_file_name)

    # Environment overrides (e.g., ACM_CONSOLE_LEVEL / EVAL_CONSOLE_LEVEL)
    env_console = os.environ.get(f"{prefix}_CONSOLE_LEVEL", None)
    env_file = os.environ.get(f"{prefix}_FILE_LEVEL", None)

    # Choose names (favor env if present)
    raw_console = (env_console or cfg_console or default_console_name)
    raw_file = (env_file or cfg_file or default_file_name)

    # Normalize names for UI (Low/Medium/High) if possible
    norm_console_name = _NORMALIZED_NAMES.get(str(raw_console).lower(), str(raw_console))
    norm_file_name = _NORMALIZED_NAMES.get(str(raw_file).lower(), str(raw_file))

    # Compute ints with sensible defaults matching normalization
    def _default_console_int(name: str) -> int:
        return _LEVELS.get(name.lower(), _LEVELS["low"])["console"]

    def _default_file_int(name: str) -> int:
        return _LEVELS.get(name.lower(), _LEVELS["medium"])["file"]

    console_level = _name_or_int(raw_console, _default_console_int(norm_console_name))
    file_level = _name_or_int(raw_file, _default_file_int(norm_file_name))

    return norm_console_name, norm_file_name, int(console_level), int(file_level)


def build_logger(name: str, console_level: int, file_level: int, log_dir: str | None = None) -> logging.Logger:
    """
    Build or reconfigure a named logger with:
      - StreamHandler at console_level
      - RotatingFileHandler at file_level (logs/acm_session.log by default)
    """
    logger = logging.getLogger(name)
    logger.setLevel(min(console_level, file_level))

    # Remove existing handlers to avoid duplicates on hot reload
    for h in list(logger.handlers):
        try:
            logger.removeHandler(h)
        except Exception:
            pass

    # Console
    sh = logging.StreamHandler()
    sh.setLevel(console_level)
    sh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(sh)

    # File
    try:
        if log_dir is None:
            # Default to a 'logs' folder next to this module
            here = os.path.dirname(os.path.abspath(__file__))
            log_dir = os.path.abspath(os.path.join(here, "..", "logs"))
        os.makedirs(log_dir, exist_ok=True)
        fh_path = os.path.join(log_dir, "acm_session.log")
        fh = RotatingFileHandler(fh_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        fh.setLevel(file_level)
        fh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(fh)
    except Exception:
        # If file handler fails, proceed with console-only
        pass

    # Do not propagate to root to avoid double logging
    logger.propagate = False
    return logger


def emit_health(logger: logging.Logger, console_name: str, file_name: str, console_level: int, file_level: int) -> None:
    """
    Emit a one-line health/config banner.
    """
    try:
        logger.info(
            "[LOG_CFG] console=%s(%s) file=%s(%s)",
            console_name, logging.getLevelName(console_level),
            file_name, logging.getLevelName(file_level),
        )
    except Exception:
        # Silent failure; logging should not crash pipeline
        pass
