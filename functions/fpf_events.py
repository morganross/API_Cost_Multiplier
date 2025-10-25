"""
FPF event parsing utilities.

Parses FilePromptForge log lines into structured events for orchestration:
- Concurrency advertisement
- RUN_START
- RUN_COMPLETE

API:
- parse_line(line: str) -> list[dict]
"""

from __future__ import annotations

import re
from typing import List, Dict, Any, Optional

# Patterns
CONCURRENCY_RE = re.compile(
    r"FPF concurrency:\s+enabled=(\w+),\s+max_concurrency=(\d+),\s+qps=([\d.]+)"
)

RUN_START_RE = re.compile(
    r"\[FPF RUN_START\]\s+id=(\S+)\s+kind=(\S+)\s+provider=(\S+)\s+model=(\S+)\s+file_b=(.+?)\s+out=(\S+|na)\s+attempt=(\d+/\d+)"
)

RUN_COMPLETE_RE = re.compile(
    r"\[FPF RUN_COMPLETE\]\s+id=(\S+)\s+kind=(\S+)\s+provider=(\S+)\s+model=(\S+)\s+ok=(true|false)\s+elapsed=([\d.]+|na)s\s+status=(\S+)\s+path=(\S+|na)\s+error=(.*)"
)


def _determine_kind(provider: Optional[str], model: Optional[str], fallback: Optional[str] = None) -> str:
    """
    Normalize kind to 'rest' or 'deep'.
    - deep if provider == openaidp or model contains 'deep-research'
    - else rest
    """
    try:
        p = (provider or "").strip().lower()
        m = (model or "").strip().lower()
        if p == "openaidp":
            return "deep"
        if "deep-research" in m:
            return "deep"
    except Exception:
        pass
    if fallback in ("rest", "deep"):
        return fallback  # trust the line if provided
    return "rest"


def parse_line(line: str) -> List[Dict[str, Any]]:
    """
    Parse a single log line and return zero or more structured events.
    Each event is a dict with:
      - type: 'concurrency' | 'run_start' | 'run_complete'
      - id, kind, provider, model, file_b, out, attempt
      - ok, elapsed_s, status, path, error
      - enabled, max_concurrency, qps
    """
    events: List[Dict[str, Any]] = []
    if not line:
        return events

    s = line.strip()

    # Concurrency line
    m = CONCURRENCY_RE.search(s)
    if m:
        try:
            enabled = str(m.group(1)).strip().lower() in ("1", "true", "yes", "on")
        except Exception:
            enabled = True
        try:
            max_c = int(m.group(2))
        except Exception:
            max_c = 1
        try:
            qps = float(m.group(3))
        except Exception:
            qps = 0.0
        events.append(
            {
                "type": "concurrency",
                "enabled": enabled,
                "max_concurrency": max(1, max_c),
                "qps": qps,
            }
        )
        return events

    # RUN_START
    m = RUN_START_RE.search(s)
    if m:
        _id = m.group(1)
        kind_raw = m.group(2)
        provider = m.group(3)
        model = m.group(4)
        file_b = m.group(5)
        out = m.group(6)
        attempt = m.group(7)
        kind = _determine_kind(provider, model, fallback=kind_raw)
        events.append(
            {
                "type": "run_start",
                "id": _id,
                "kind": kind,
                "provider": provider,
                "model": model,
                "file_b": file_b,
                "out": out,
                "attempt": attempt,
            }
        )
        return events

    # RUN_COMPLETE
    m = RUN_COMPLETE_RE.search(s)
    if m:
        _id = m.group(1)
        kind_raw = m.group(2)
        provider = m.group(3)
        model = m.group(4)
        ok_str = (m.group(5) or "").strip().lower()
        ok = ok_str == "true"
        elapsed_raw = m.group(6)
        try:
            elapsed_s = float(elapsed_raw) if (elapsed_raw and elapsed_raw != "na") else None
        except Exception:
            elapsed_s = None
        status = m.group(7)
        path = m.group(8)
        error = (m.group(9) or "").strip()
        kind = _determine_kind(provider, model, fallback=kind_raw)
        events.append(
            {
                "type": "run_complete",
                "id": _id,
                "kind": kind,
                "provider": provider,
                "model": model,
                "ok": ok,
                "elapsed_s": elapsed_s,
                "status": status,
                "path": path,
                "error": error,
            }
        )
        return events

    return events
