"""
Watermark-driven orchestration for ACM.

Coordinates:
- Start FPF openaidp (deep) and FPF rest batches immediately.
- Track FPF events to maintain inflight counts and effective max concurrency.
- Launch GPT‑R standard group when there is headroom on FPF-rest.
- After GPT‑R standard completes, launch GPT‑R deep group when headroom holds.
- Never gate on openaidp; optionally await openaidp at shutdown.

API:
- async run_for_file(
    md: str,
    config: dict,
    entries: list[dict],
    iterations: int,
    keep_temp: bool,
    forward_subprocess_output: bool,
    low_watermark: int | None = None,
    await_open_at_shutdown: bool = False,
    launch_gptr=None,   # callable: (idx:int, entry:dict) -> asyncio.Task
    launch_dr=None,     # callable: (idx:int, entry:dict) -> asyncio.Task
    run_fpf_batch=None  # callable: (run_id:str, entries:list[dict], on_event:callable) -> asyncio.Task
  ) -> tuple[list, list]
    Returns (rest_tasks, open_tasks) so caller can decide what to await.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable, Awaitable, Optional, Tuple, List, Dict, Any

from .fpf_inflight import FpfInflightTracker


async def _wait_for_headroom(tracker: Optional[FpfInflightTracker], low_watermark: Optional[int]) -> None:
    if tracker is None:
        return
    while True:
        try:
            hr = tracker.headroom(low_watermark=low_watermark)
            if hr.get("ready", False):
                return
            await asyncio.sleep(0.5)
        except Exception:
            # Best-effort; avoid blocking on telemetry failures
            await asyncio.sleep(0.5)


async def run_for_file(
    md: str,
    config: dict,
    entries: list[dict],
    iterations: int,
    keep_temp: bool,
    forward_subprocess_output: bool,
    low_watermark: Optional[int] = None,
    await_open_at_shutdown: bool = False,
    launch_gptr: Optional[Callable[[int, dict], Awaitable[asyncio.Task]]] = None,
    launch_dr: Optional[Callable[[int, dict], Awaitable[asyncio.Task]]] = None,
    run_fpf_batch: Optional[Callable[[str, list[dict], Callable[[dict], None]], Awaitable[asyncio.Task]]] = None,
) -> Tuple[list, list]:
    # Classify configured runs for this file
    fpf_entries: list[dict] = []
    gptr_entries: list[tuple[int, dict]] = []
    dr_entries: list[tuple[int, dict]] = []
    ma_entries: list[tuple[int, dict]] = []

    for idx, entry in enumerate(entries):
        rtype = (entry.get("type") or "").strip().lower()
        if rtype == "fpf":
            fpf_entries.append(entry)
        elif rtype == "gptr":
            gptr_entries.append((idx, entry))
        elif rtype == "dr":
            dr_entries.append((idx, entry))
        elif rtype == "ma":
            ma_entries.append((idx, entry))
        else:
            # Unknown types are ignored here; caller may handle separately
            pass

    # Split FPF into deep(openaidp) vs rest
    fpf_openaidp = [e for e in fpf_entries if (e.get("provider") or "").strip().lower() == "openaidp"]
    fpf_rest = [e for e in fpf_entries if (e.get("provider") or "").strip().lower() != "openaidp"]

    # Initialize inflight tracker for watermark gating
    totals_rest = len(fpf_rest) * int(iterations)
    totals_deep = len(fpf_openaidp) * int(iterations)
    tracker = FpfInflightTracker({"rest": totals_rest, "deep": totals_deep})

    # Launch FPF batches immediately (non-blocking)
    rest_task: asyncio.Task | None = None
    open_task: asyncio.Task | None = None
    rest_tasks: list = []
    open_tasks: list = []

    async def _run_fpf(run_id: str, group_entries: list[dict]):
        if run_fpf_batch is None or not group_entries:
            return None
        return await run_fpf_batch(run_id, group_entries, tracker.update)

    if fpf_openaidp:
        run_id_open = f"fpf-openAidp-{Path(md).stem}"
        open_task = asyncio.create_task(_run_fpf(run_id_open, fpf_openaidp))
        open_tasks.append(open_task)

    if fpf_rest:
        run_id_rest = f"fpf-rest-{Path(md).stem}"
        rest_task = asyncio.create_task(_run_fpf(run_id_rest, fpf_rest))
        rest_tasks.append(rest_task)

    # Watermark-gated GPT‑R standard group
    await _wait_for_headroom(tracker, low_watermark)
    if launch_gptr and gptr_entries:
        std_tasks: list[asyncio.Task] = []
        for idx, e in gptr_entries:
            # Delegate concurrency/launch pacing to provided wrapper
            t = await launch_gptr(idx, e)
            if isinstance(t, asyncio.Task):
                std_tasks.append(t)
        if std_tasks:
            await asyncio.gather(*std_tasks, return_exceptions=False)

    # Watermark-gated GPT‑R deep group (after std completes)
    await _wait_for_headroom(tracker, low_watermark)
    if launch_dr and dr_entries:
        dr_tasks: list[asyncio.Task] = []
        for idx, e in dr_entries:
            t = await launch_dr(idx, e)
            if isinstance(t, asyncio.Task):
                dr_tasks.append(t)
        if dr_tasks:
            await asyncio.gather(*dr_tasks, return_exceptions=False)

    # Optionally await openaidp at shutdown
    if await_open_at_shutdown and open_tasks:
        await asyncio.gather(*[t for t in open_tasks if t is not None], return_exceptions=False)

    # Always return task lists; caller can choose to await rest tasks for correctness
    return rest_tasks, open_tasks
