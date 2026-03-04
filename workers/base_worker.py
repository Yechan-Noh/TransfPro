"""Base worker class for background operations.

This module provides the base QObject worker class that all background
workers inherit from. It handles threading, signals, and error handling.
"""

import logging
import threading
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot


class BaseWorker(QObject):
    """Base class for all background workers.

    Provides standard signals and error handling pattern.
    Subclasses must implement the do_work() method.

    Signals:
        finished: Emitted when the worker completes (successfully or with error)
        error: Emitted when an exception occurs during work
        status_message: Emitted to provide status updates
    """

    finished = pyqtSignal()
    error = pyqtSignal(str)
    status_message = pyqtSignal(str)

    def __init__(self):
        """Initialize the base worker."""
        super().__init__()
        self.logger = logging.getLogger(self.__class__.__name__)
        self._cancel_event = threading.Event()

    @pyqtSlot()
    def run(self):
        """Main entry point called when thread starts.

        This method handles exception catching and ensures finished signal
        is always emitted. Subclasses should not override this method;
        instead implement do_work().
        """
        try:
            self.do_work()
        except Exception as e:
            self.logger.error(f"Worker error: {e}", exc_info=True)
            self.error.emit(str(e))
        finally:
            self.finished.emit()

    def do_work(self):
        """Perform the actual work.

        This method must be implemented by subclasses to define
        the work that should be executed in the background thread.

        Raises:
            NotImplementedError: If not implemented by subclass
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement do_work() method"
        )

    def cancel(self):
        """Request cancellation of the worker.

        Sets the cancellation flag. The worker should check is_cancelled
        periodically during long-running operations and exit gracefully.
        Uses threading.Event for proper cross-thread visibility.
        """
        self._cancel_event.set()
        self.logger.debug(f"{self.__class__.__name__} cancellation requested")

    @property
    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested.

        Returns:
            True if cancel() was called, False otherwise
        """
        return self._cancel_event.is_set()
