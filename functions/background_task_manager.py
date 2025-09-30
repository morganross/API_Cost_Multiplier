"""
Background Task Manager for OpenAI Deep Research tasks only.

This module provides background task support specifically for OpenAI Deep Research models
(openaidp provider). Non-configurable and always enabled for these tasks.
"""

from __future__ import annotations

import asyncio
import time
import uuid
import os
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Callable, Optional, Any
import logging

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskConfig:
    """Configuration for a background task"""
    task_type: str  # "dr" for deep research
    provider: str   # "openaidp"
    model: str      # model name
    prompt: str     # research prompt
    run_index: int  # which run this is
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskResult:
    """Result of a completed background task"""
    task_id: str
    status: TaskStatus
    output_path: Optional[str] = None
    model_used: Optional[str] = None
    error_message: Optional[str] = None
    execution_time: Optional[float] = None


@dataclass
class BackgroundTask:
    """Individual background task instance"""
    task_id: str
    config: TaskConfig
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    current_operation: str = ""
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    result: Optional[TaskResult] = None
    error_message: Optional[str] = None
    cancelled: bool = False

    def update_progress(self, progress: float, operation: str):
        """Update task progress"""
        self.progress = max(0.0, min(1.0, progress))
        self.current_operation = operation

    def mark_completed(self, result: TaskResult):
        """Mark task as completed"""
        self.status = TaskStatus.COMPLETED
        self.end_time = time.time()
        self.result = result

    def mark_failed(self, error: str):
        """Mark task as failed"""
        self.status = TaskStatus.FAILED
        self.end_time = time.time()
        self.error_message = error


class BackgroundTaskManager:
    """Manages background tasks for OpenAI Deep Research"""

    def __init__(self):
        self.active_tasks: Dict[str, BackgroundTask] = {}
        self.completed_tasks: Dict[str, TaskResult] = {}
        self.progress_callbacks: Dict[str, List[Callable]] = {}
        self.polling_interval = 15  # seconds

    def should_use_background(self, task_config: TaskConfig) -> bool:
        """Check if task should use background processing (OpenAI DP DR only)"""
        return (task_config.task_type == "dr" and
                task_config.provider == "openaidp")

    def submit_task(self, config: TaskConfig) -> str:
        """Submit a new background task"""
        if not self.should_use_background(config):
            raise ValueError(f"Task type {config.task_type} with provider {config.provider} not supported for background processing")

        task_id = str(uuid.uuid4())
        task = BackgroundTask(task_id=task_id, config=config)

        self.active_tasks[task_id] = task
        logger.info(f"Submitted background task {task_id} for {config.provider}:{config.model}")

        # Start background execution
        asyncio.create_task(self._execute_task(task))

        return task_id

    def register_progress_callback(self, task_id: str, callback: Callable):
        """Register a callback for task progress updates"""
        if task_id not in self.progress_callbacks:
            self.progress_callbacks[task_id] = []
        self.progress_callbacks[task_id].append(callback)

    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """Get current status of a task"""
        if task_id in self.active_tasks:
            task = self.active_tasks[task_id]
            return {
                "task_id": task_id,
                "status": task.status.value,
                "progress": task.progress,
                "current_operation": task.current_operation,
                "start_time": task.start_time
            }
        elif task_id in self.completed_tasks:
            result = self.completed_tasks[task_id]
            return {
                "task_id": task_id,
                "status": result.status.value,
                "progress": 1.0,
                "output_path": result.output_path,
                "model_used": result.model_used,
                "error_message": result.error_message,
                "execution_time": result.execution_time
            }
        return None

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task"""
        if task_id in self.active_tasks:
            self.active_tasks[task_id].cancelled = True
            return True
        return False

    def _notify_progress(self, task_id: str, progress: float, operation: str):
        """Notify all registered callbacks of progress update"""
        if task_id in self.progress_callbacks:
            for callback in self.progress_callbacks[task_id]:
                try:
                    callback(task_id, progress, operation)
                except Exception as e:
                    logger.error(f"Error in progress callback: {e}")

    async def _execute_task(self, task: BackgroundTask):
        """Execute a background task"""
        try:
            task.status = TaskStatus.QUEUED
            task.start_time = time.time()
            self._notify_progress(task.task_id, 0.1, "Queued")
            print(f"[DR background] task={task.task_id[:8]} status=queued", flush=True)

            # Import here to avoid circular imports
            from . import gpt_researcher_client

            # Use OpenAI background mode for Deep Research
            task.status = TaskStatus.IN_PROGRESS
            task.update_progress(0.2, "Submitting to OpenAI...")
            print(f"[DR background] task={task.task_id[:8]} status=in_progress stage=submitting", flush=True)

            # Submit with background=True
            response = await gpt_researcher_client.submit_deep_research_background(
                prompt=task.config.prompt,
                model=task.config.model
            )

            if not response or not hasattr(response, 'id'):
                raise RuntimeError("Failed to submit background task to OpenAI")

            response_id = response.id
            # Persist response mapping for reconciliation
            try:
                repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                tasks_dir = os.path.join(repo_root, "temp_gpt_researcher_reports", "_background_tasks")
                os.makedirs(tasks_dir, exist_ok=True)
                record_path = os.path.join(tasks_dir, f"{task.task_id}.json")
                record = {
                    "task_id": task.task_id,
                    "response_id": response_id,
                    "provider": task.config.provider,
                    "model": task.config.model,
                    "run_index": task.config.run_index,
                    "created_at": time.time(),
                    "status": "submitted",
                    "prompt_preview": (task.config.prompt[:200] + "…") if task.config.prompt else ""
                }
                with open(record_path, "w", encoding="utf-8") as fh:
                    json.dump(record, fh, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Failed to persist background task record: {e}")
            task.update_progress(0.3, "Research in progress...")

            # Poll for completion
            max_polls = 120  # 30 minutes max (120 * 15 seconds)
            poll_count = 0

            while poll_count < max_polls:
                if task.cancelled:
                    task.status = TaskStatus.CANCELLED
                    print(f"[DR background] task={task.task_id[:8]} status=cancelled", flush=True)
                    return

                # Check status
                status_response = await gpt_researcher_client.get_response_status(response_id)

                if status_response.status == "completed":
                    task.update_progress(0.9, "Fetching results...")

                    # Get final results
                    final_response = await gpt_researcher_client.get_response_results(response_id)

                    # Extract output path and model info
                    output_path = None
                    model_used = task.config.model

                    if final_response and hasattr(final_response, 'content'):
                        # This would need to be implemented based on actual response structure
                        output_path = "path_extraction_needed"  # Placeholder

                    execution_time = time.time() - task.start_time
                    result = TaskResult(
                        task_id=task.task_id,
                        status=TaskStatus.COMPLETED,
                        output_path=output_path,
                        model_used=model_used,
                        execution_time=execution_time
                    )

                    task.mark_completed(result)
                    self.completed_tasks[task.task_id] = result
                    self._notify_progress(task.task_id, 1.0, "Completed")

                    logger.info(f"Background task {task.task_id} completed in {execution_time:.1f}s")
                    print(f"[DR background] task={task.task_id[:8]} status=completed elapsed={execution_time:.1f}s", flush=True)
                    break

                elif status_response.status in ["failed", "cancelled"]:
                    execution_time = time.time() - task.start_time
                    error_msg = f"OpenAI task {status_response.status}"
                    result = TaskResult(
                        task_id=task.task_id,
                        status=TaskStatus.FAILED,
                        error_message=error_msg,
                        execution_time=execution_time
                    )

                    task.mark_failed(error_msg)
                    self.completed_tasks[task.task_id] = result
                    self._notify_progress(task.task_id, 0.0, f"Failed: {error_msg}")
                    print(f"[DR background] task={task.task_id[:8]} status={status_response.status} elapsed={execution_time:.1f}s", flush=True)
                    break

                else:
                    # Still in progress or queued
                    progress = 0.3 + (poll_count / max_polls) * 0.6
                    task.update_progress(progress, f"Status: {status_response.status}")
                    self._notify_progress(task.task_id, progress, f"Status: {status_response.status}")
                    print(f"[DR background] task={task.task_id[:8]} status={status_response.status} progress={int(progress*100)}%", flush=True)

                poll_count += 1
                await asyncio.sleep(self.polling_interval)

            if poll_count >= max_polls:
                # Timeout
                error_msg = "Task timed out after 30 minutes"
                task.mark_failed(error_msg)
                result = TaskResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    error_message=error_msg,
                    execution_time=time.time() - task.start_time
                )
                self.completed_tasks[task.task_id] = result
                print(f"[DR background] task={task.task_id[:8]} status=timeout", flush=True)

        except Exception as e:
            error_msg = f"Background task execution failed: {str(e)}"
            logger.error(error_msg, exc_info=True)

            task.mark_failed(error_msg)
            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                error_message=error_msg,
                execution_time=time.time() - task.start_time if task.start_time else 0
            )
            self.completed_tasks[task.task_id] = result

        finally:
            # Clean up active task
            if task.task_id in self.active_tasks:
                del self.active_tasks[task.task_id]


# Global task manager instance
_task_manager = None

def get_task_manager() -> BackgroundTaskManager:
    """Get the global task manager instance"""
    global _task_manager
    if _task_manager is None:
        _task_manager = BackgroundTaskManager()
    return _task_manager

def reset_task_manager():
    """Reset the global task manager (for testing)"""
    global _task_manager
    _task_manager = None