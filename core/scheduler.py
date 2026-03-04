"""Periodic task scheduler using Qt timers."""

import logging
from typing import Dict, Callable, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ScheduledTask:
    """Represents a scheduled task."""
    name: str
    callback: Callable
    interval_ms: int
    is_active: bool = True
    timer_ref: Optional[object] = None


class PeriodicScheduler:
    """Schedule periodic tasks using Qt timers.

    This scheduler manages recurring background tasks that execute at
    specified intervals. It requires Qt to be available.
    """

    def __init__(self):
        """Initialize periodic scheduler."""
        self._timers: Dict[str, ScheduledTask] = {}
        self._qt_available = False

        # Try to import Qt
        try:
            from PyQt5.QtCore import QTimer
            self._QTimer = QTimer
            self._qt_available = True
            logger.debug("Qt available for scheduler")
        except ImportError:
            logger.warning("Qt not available, scheduler will operate in fallback mode")

    def add_task(
        self,
        name: str,
        callback: Callable,
        interval_ms: int
    ) -> bool:
        """
        Add a periodic task.

        Args:
            name: Unique task name
            callback: Function to call periodically. Should take no arguments.
            interval_ms: Interval in milliseconds between executions

        Returns:
            True if task was added successfully

        Raises:
            ValueError if task name already exists
            RuntimeError if Qt is not available
        """
        if name in self._timers:
            raise ValueError(f"Task '{name}' already exists")

        if not self._qt_available:
            raise RuntimeError("Qt is not available for scheduler")

        try:
            # Create Qt timer
            timer = self._QTimer()
            timer.timeout.connect(callback)
            timer.start(interval_ms)

            # Store task info
            task = ScheduledTask(
                name=name,
                callback=callback,
                interval_ms=interval_ms,
                is_active=True,
                timer_ref=timer
            )
            self._timers[name] = task

            logger.info(f"Added task '{name}' with interval {interval_ms}ms")
            return True

        except Exception as e:
            logger.error(f"Failed to add task '{name}': {e}")
            raise

    def remove_task(self, name: str) -> bool:
        """
        Remove a scheduled task.

        Args:
            name: Task name

        Returns:
            True if task was removed, False if not found
        """
        if name not in self._timers:
            logger.warning(f"Task '{name}' not found")
            return False

        try:
            task = self._timers[name]
            if task.timer_ref:
                task.timer_ref.stop()

            del self._timers[name]
            logger.info(f"Removed task '{name}'")
            return True

        except Exception as e:
            logger.error(f"Failed to remove task '{name}': {e}")
            return False

    def update_interval(self, name: str, interval_ms: int) -> bool:
        """
        Update the interval of a scheduled task.

        Args:
            name: Task name
            interval_ms: New interval in milliseconds

        Returns:
            True if interval was updated

        Raises:
            ValueError if task not found
        """
        if name not in self._timers:
            raise ValueError(f"Task '{name}' not found")

        try:
            task = self._timers[name]
            if task.timer_ref:
                task.timer_ref.stop()
                task.timer_ref.start(interval_ms)

            task.interval_ms = interval_ms
            logger.info(f"Updated task '{name}' interval to {interval_ms}ms")
            return True

        except Exception as e:
            logger.error(f"Failed to update interval for '{name}': {e}")
            raise

    def pause_task(self, name: str) -> bool:
        """
        Pause a scheduled task (stop execution but keep registered).

        Args:
            name: Task name

        Returns:
            True if task was paused

        Raises:
            ValueError if task not found
        """
        if name not in self._timers:
            raise ValueError(f"Task '{name}' not found")

        try:
            task = self._timers[name]
            if task.timer_ref:
                task.timer_ref.stop()

            task.is_active = False
            logger.info(f"Paused task '{name}'")
            return True

        except Exception as e:
            logger.error(f"Failed to pause task '{name}': {e}")
            raise

    def resume_task(self, name: str) -> bool:
        """
        Resume a paused scheduled task.

        Args:
            name: Task name

        Returns:
            True if task was resumed

        Raises:
            ValueError if task not found
        """
        if name not in self._timers:
            raise ValueError(f"Task '{name}' not found")

        try:
            task = self._timers[name]
            if task.timer_ref:
                task.timer_ref.start(task.interval_ms)

            task.is_active = True
            logger.info(f"Resumed task '{name}'")
            return True

        except Exception as e:
            logger.error(f"Failed to resume task '{name}': {e}")
            raise

    def is_task_active(self, name: str) -> bool:
        """
        Check if a task is currently active.

        Args:
            name: Task name

        Returns:
            True if task exists and is active
        """
        if name not in self._timers:
            return False

        return self._timers[name].is_active

    def get_task_info(self, name: str) -> Optional[Dict]:
        """
        Get information about a scheduled task.

        Args:
            name: Task name

        Returns:
            Dictionary with task info, or None if not found
        """
        if name not in self._timers:
            return None

        task = self._timers[name]
        return {
            'name': task.name,
            'interval_ms': task.interval_ms,
            'is_active': task.is_active,
            'callback': task.callback.__name__ if hasattr(task.callback, '__name__') else str(task.callback)
        }

    def list_tasks(self) -> Dict[str, Dict]:
        """
        List all scheduled tasks.

        Returns:
            Dictionary mapping task name to task info
        """
        tasks = {}
        for name, task in self._timers.items():
            tasks[name] = {
                'interval_ms': task.interval_ms,
                'is_active': task.is_active,
                'callback': task.callback.__name__ if hasattr(task.callback, '__name__') else str(task.callback)
            }
        return tasks

    def stop_all(self):
        """Stop all scheduled tasks."""
        logger.info(f"Stopping all {len(self._timers)} tasks")

        for name, task in list(self._timers.items()):
            try:
                if task.timer_ref:
                    task.timer_ref.stop()
                logger.debug(f"Stopped task '{name}'")
            except Exception as e:
                logger.warning(f"Error stopping task '{name}': {e}")

        self._timers.clear()
        logger.info("All tasks stopped")

    def __del__(self):
        """Cleanup when scheduler is destroyed."""
        try:
            self.stop_all()
        except Exception as e:
            logger.debug(f"Error during scheduler cleanup: {e}")
