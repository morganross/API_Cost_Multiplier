"""
Utility helpers for process_markdown refactor.

Contains:
- start_heartbeat
- ensure_temp_dir
- sanitize_model_for_filename
- normalize_report_entries
- load_env_file (simple .env parser)
"""

from __future__ import annotations

import os
import re
import threading
import time
from typing import Iterable, List, Tuple, Optional


def start_heartbeat(label: str = "process_markdown_noeval", interval: float = 3.0) -> threading.Event:
    """
    Start a daemon heartbeat thread that prints a short message every `interval` seconds.
    Returns a threading.Event you can set() to stop the heartbeat.
    """
    stop_event = threading.Event()

    def _hb():
        counter = 0
        while not stop_event.is_set():
            counter += 1
            print(f"[HEARTBEAT {label}] alive ({counter})", flush=True)
            # wait with timeout so stop_event can interrupt
            stop_event.wait(interval)

    t = threading.Thread(target=_hb, daemon=True)
    t.start()
    return stop_event


def ensure_temp_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def sanitize_model_for_filename(model: Optional[str]) -> str:
    """
    Convert a raw model string to a safe, short filename component.
    Behavior:
      - If model is None or empty -> "unknown-model"
      - If contains ":" (provider:model) -> take the part after the first colon (model only)
      - Lowercase, replace non-alphanum (except .,_,-) with '-'
      - Collapse repeated '-' and strip leading/trailing '-'
      - Truncate to 60 chars
    """
    if not model:
        return "unknown-model"
    # If provider included like "openai:gpt-4o", take the model only (after first colon)
    if ":" in model:
        try:
            model = model.split(":", 1)[1]
        except Exception:
            pass
    s = str(model).lower()
    # Replace any sequence of characters that are not a-z0-9._- with a single hyphen
    s = re.sub(r"[^a-z0-9._-]+", "-", s)
    # Collapse multiple hyphens
    s = re.sub(r"-{2,}", "-", s)
    s = s.strip("-")
    if not s:
        return "unknown-model"
    return s[:60]


def normalize_report_entries(results: Iterable) -> List[Tuple[str, Optional[str]]]:
    """
    Normalize entries returned by run functions.

    Input items may be:
      - tuple/list: (path, model_name)
      - str: path

    Returns list of tuples: [(abs_path, model_name_or_none), ...]
    """
    normalized: List[Tuple[str, Optional[str]]] = []
    for res in results:
        model = None
        if isinstance(res, (tuple, list)):
            path = res[0]
            if len(res) > 1:
                model = res[1]
        else:
            path = res
        if path:
            normalized.append((os.path.abspath(path), model))
    return normalized


def load_env_file(path: str) -> dict:
    """
    Very small .env parser: returns dict of key -> value for lines containing '='.
    Lines starting with '#' or blank lines are ignored.
    """
    env = {}
    if not path or not os.path.exists(path):
        return env
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k:
                    env.setdefault(k, v)
    except Exception:
        # non-fatal; return what we've parsed so far
        pass
    return env
