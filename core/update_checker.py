"""
Auto-update version checker for TransfPro.

Performs a non-blocking HTTP check against a configurable version endpoint
to determine whether a newer release is available. Emits a Qt signal so the
UI can show an "Update available" banner without blocking startup.
"""

import json
import logging
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from transfpro.config.constants import APP_VERSION

logger = logging.getLogger(__name__)

# Default endpoint — override via Settings key "updates/version_url"
DEFAULT_VERSION_URL = "https://transfpro.com/api/version.json"
# Expected JSON format:  {"version": "1.2.0", "url": "https://transfpro.com/download"}


class _VersionCheckWorker(QObject):
    """Background worker that fetches the remote version."""

    update_available = pyqtSignal(str, str)  # (latest_version, download_url)
    finished = pyqtSignal()

    def __init__(self, url: str, current_version: str):
        super().__init__()
        self._url = url
        self._current = current_version

    def run(self):
        try:
            req = Request(self._url, headers={"User-Agent": f"TransfPro/{self._current}"})
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            latest = data.get("version", "")
            download_url = data.get("url", "")
            if latest and self._is_newer(latest, self._current):
                self.update_available.emit(latest, download_url)
                logger.info(f"Update available: {latest}")
            else:
                logger.debug("Application is up to date")
        except (URLError, json.JSONDecodeError, OSError) as e:
            logger.debug(f"Update check skipped: {e}")
        finally:
            self.finished.emit()

    @staticmethod
    def _is_newer(remote: str, local: str) -> bool:
        """Compare simple semver strings (e.g. '1.2.3')."""
        try:
            remote_parts = [int(x) for x in remote.split(".")]
            local_parts = [int(x) for x in local.split(".")]
            return remote_parts > local_parts
        except (ValueError, AttributeError):
            return False


class UpdateChecker(QObject):
    """
    Non-blocking update checker.

    Usage::

        checker = UpdateChecker(version_url="https://...")
        checker.update_available.connect(on_update)
        checker.check()  # runs in background thread
    """

    update_available = pyqtSignal(str, str)  # (latest_version, download_url)

    def __init__(self, version_url: Optional[str] = None, parent=None):
        super().__init__(parent)
        self._url = version_url or DEFAULT_VERSION_URL
        self._thread: Optional[QThread] = None
        self._worker: Optional[_VersionCheckWorker] = None

    def check(self):
        """Start a background update check."""
        if self._thread is not None and self._thread.isRunning():
            return  # Already checking

        self._thread = QThread()
        self._worker = _VersionCheckWorker(self._url, APP_VERSION)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.update_available.connect(self.update_available)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._cleanup)

        self._thread.start()
        logger.debug("Update check started")

    def _cleanup(self):
        self._thread = None
        self._worker = None
