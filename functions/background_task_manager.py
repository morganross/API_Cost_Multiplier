"""
Deprecated: Background task system removed.

This module is intentionally left as a stub to prevent accidental usage.
Any attempt to import/use background task functionality should fail fast.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class _Removed:
    """Placeholder dataclass to keep old type names importable but unusable."""
    def __post_init__(self):
        raise RuntimeError("Background tasks have been removed from this project.")


# Legacy names kept only to avoid hard ImportError during transition.
# Using any of these will raise at runtime with a clear message.
TaskStatus = _Removed
TaskConfig = _Removed
TaskResult = _Removed
BackgroundTask = _Removed


class BackgroundTaskManager:
    def __init__(self) -> None:
        raise RuntimeError("Background tasks have been removed from this project.")


def get_task_manager() -> BackgroundTaskManager:
    raise RuntimeError("Background tasks have been removed from this project.")


def reset_task_manager() -> None:
    # No-op: background tasks are removed
    return
