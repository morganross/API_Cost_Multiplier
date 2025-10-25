"""
Inflight tracking for FilePromptForge runs.

Tracks:
- inflight (rest/deep)
- completed (rest/deep)
- totals provided upfront (rest/deep)
- effective max concurrency (eff_max) learned from events

API:
- FpfInflightTracker.update(event: dict) -> None
- FpfInflightTracker.headroom(low_watermark: int | None = None) -> dict
- FpfInflightTracker.snapshot() -> dict
"""

from __future__ import annotations

from typing import Dict, Any, Optional
import threading


class FpfInflightTracker:
    def __init__(self, totals: Dict[str, int], eff_max: Optional[int] = None) -> None:
        """
        totals: {"rest": int, "deep": int}
        eff_max: optional explicit concurrency ceiling for REST group.
                 If None, will be set upon receiving a 'concurrency' event; otherwise defaults to totals['rest'] or 1.
        """
        self._lock = threading.Lock()
        self.totals = {
            "rest": int(totals.get("rest", 0)),
            "deep": int(totals.get("deep", 0)),
        }
        self.inflight = {"rest": 0, "deep": 0}
        self.completed = {"rest": 0, "deep": 0}
        self.eff_max = int(eff_max) if eff_max is not None else None

    def _eff_max_or_default(self) -> int:
        # Default to totals["rest"] if no concurrency event seen; clamp to at least 1
        base = self.eff_max if self.eff_max is not None else max(1, int(self.totals.get("rest", 1)) or 1)
        return max(1, int(base))

    def update(self, event: Dict[str, Any]) -> None:
        """
        Update state based on parsed event dict.
        Expected event types:
          - {"type": "concurrency", "max_concurrency": int}
          - {"type": "run_start", "kind": "rest"|"deep"}
          - {"type": "run_complete", "kind": "rest"|"deep"}
        """
        if not isinstance(event, dict):
            return
        etype = str(event.get("type", "")).strip().lower()
        with self._lock:
            if etype == "concurrency":
                try:
                    mc = int(event.get("max_concurrency", 1))
                    self.eff_max = max(1, mc)
                except Exception:
                    # Keep prior eff_max if parse fails
                    pass
                return

            if etype == "run_start":
                k = str(event.get("kind", "rest")).strip().lower()
                if k not in self.inflight:
                    k = "rest"
                self.inflight[k] = max(0, int(self.inflight.get(k, 0)) + 1)
                return

            if etype == "run_complete":
                k = str(event.get("kind", "rest")).strip().lower()
                if k not in self.inflight:
                    k = "rest"
                # Decrement inflight and increment completed
                self.inflight[k] = max(0, int(self.inflight.get(k, 0)) - 1)
                self.completed[k] = max(0, int(self.completed.get(k, 0)) + 1)
                return

    def headroom(self, low_watermark: Optional[int] = None) -> Dict[str, Any]:
        """
        Compute readiness and availability for launching GPT‑R based on FPF-rest inflight.

        If low_watermark is None:
          - ready = available > 0 (i.e., inflight_rest < eff_max)

        If low_watermark is provided (>= 0):
          - ready = rest_inflight <= eff_max - low_watermark
            Example: low_watermark=1 requires at least 1 free slot before launching.

        Returns:
          {
            "eff_max": int,
            "rest_inflight": int,
            "available": int,
            "ready": bool
          }
        """
        with self._lock:
            eff = self._eff_max_or_default()
            rest_inflight = int(self.inflight.get("rest", 0))
        available = max(0, eff - rest_inflight)
        if low_watermark is None:
            ready = available > 0
        else:
            try:
                lw = max(0, int(low_watermark))
            except Exception:
                lw = 0
            ready = rest_inflight <= max(0, eff - lw)
        return {
            "eff_max": eff,
            "rest_inflight": rest_inflight,
            "available": available,
            "ready": bool(ready),
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "totals": dict(self.totals),
                "inflight": dict(self.inflight),
                "completed": dict(self.completed),
                "eff_max": self._eff_max_or_default(),
            }
