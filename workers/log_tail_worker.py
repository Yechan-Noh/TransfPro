"""Worker for live log file tailing.

This module provides a QObject worker that continuously monitors and tails
remote log files, emitting updates as new content is written.

Uses SFTP stat() and file seeking instead of SSH shell commands (dd, stat)
for better performance and lower overhead.
"""

import time
from PyQt5.QtCore import pyqtSignal

from transfpro.core.ssh_manager import SSHManager
from .base_worker import BaseWorker


class LogTailWorker(BaseWorker):
    """Background worker for tailing remote log files.

    Periodically checks a remote log file for new content and emits
    updates when the file grows. Useful for monitoring job output
    and simulation progress logs in real-time.

    Uses SFTP for file size checks and content reading, which is
    significantly faster than spawning shell commands per poll cycle.

    Signals:
        new_content: Emitted with (job_id, new_text) when file is updated
    """

    new_content = pyqtSignal(str, str)  # job_id, new_text

    def __init__(self, ssh_manager: SSHManager, job_id: str, log_path: str,
                 poll_interval: int = 5):
        """Initialize the log tail worker.

        Args:
            ssh_manager: SSHManager instance for SSH commands
            job_id: Job identifier to associate with log
            log_path: Full path to remote log file
            poll_interval: Seconds between file checks (default: 5)
        """
        super().__init__()
        self.ssh_manager = ssh_manager
        self.job_id = job_id
        self.log_path = log_path
        self.poll_interval = poll_interval
        self._last_size = 0
        self._running = True
        self._last_position = 0
        self._sftp = None  # Dedicated SFTP session for tailing

    def do_work(self):
        """Continuously tail the log file.

        Opens a dedicated SFTP session, then periodically stat()s the file
        and reads any new bytes via seek+read — no shell commands needed.
        """
        self.status_message.emit(f"Starting log tail for {self.job_id}...")
        self.logger.info(f"Tailing log file: {self.log_path} (job: {self.job_id})")

        try:
            # Open a dedicated SFTP session for this worker
            self._sftp = self.ssh_manager.open_sftp()

            # Initial file size check
            self._last_size = self._get_file_size()
            if self._last_size is None:
                raise Exception(f"Cannot access log file: {self.log_path}")

            self._last_position = self._last_size  # Start from end of file
            self.logger.debug(f"Initial log file size: {self._last_size} bytes")

            # Main tailing loop
            while self._running and not self.is_cancelled:
                try:
                    current_size = self._get_file_size()

                    if current_size is None:
                        self.logger.debug(
                            f"Log file not yet available: {self.log_path}"
                        )
                        time.sleep(self.poll_interval)
                        continue

                    # Check if file has grown
                    if current_size > self._last_size:
                        new_text = self._read_new_content(current_size)
                        if new_text:
                            self.logger.debug(
                                f"Read {len(new_text)} chars of new content"
                            )
                            self.new_content.emit(self.job_id, new_text)
                        self._last_size = current_size
                    elif current_size < self._last_size:
                        # File was truncated, reset position
                        self.logger.info(f"Log file was truncated: {self.log_path}")
                        self._last_size = current_size
                        self._last_position = 0

                except Exception as e:
                    self.logger.warning(f"Error reading log file: {e}")
                    time.sleep(self.poll_interval)
                    continue

                # Wait before next check
                time.sleep(self.poll_interval)

            self.logger.info(f"Log tail worker stopped (job: {self.job_id})")
            self.status_message.emit(f"Log tail stopped for {self.job_id}")

        except Exception as e:
            error_msg = f"Log tail error: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.status_message.emit(error_msg)
            raise
        finally:
            # Always close the dedicated SFTP session
            if self._sftp is not None:
                try:
                    self._sftp.close()
                except Exception:
                    pass
                self._sftp = None

    def _get_file_size(self) -> int:
        """Get the size of the remote log file via SFTP stat.

        Returns:
            File size in bytes, or None if file doesn't exist
        """
        try:
            attr = self._sftp.stat(self.log_path)
            return attr.st_size
        except FileNotFoundError:
            return None
        except Exception as e:
            self.logger.debug(f"Failed to stat file: {e}")
            return None

    def _read_new_content(self, current_size: int) -> str:
        """Read new content from the log file using SFTP seek+read.

        Seeks to the last-read position and reads only the new bytes.

        Args:
            current_size: Current file size in bytes

        Returns:
            New content from the file, or empty string if no new content
        """
        try:
            bytes_to_read = current_size - self._last_position
            if bytes_to_read <= 0:
                return ""

            with self._sftp.open(self.log_path, 'rb') as f:
                f.seek(self._last_position)
                data = f.read(bytes_to_read)

            self._last_position = current_size
            return data.decode('utf-8', errors='replace')

        except Exception as e:
            self.logger.warning(f"Error reading new content: {e}")
            return ""

    def stop(self):
        """Stop the log tailing.

        Gracefully stops the tailing loop. The worker will finish
        its current iteration and emit finished signal.
        """
        self._running = False
        self.logger.debug(f"Stop requested for log tail (job: {self.job_id})")
