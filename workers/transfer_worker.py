"""Worker for background file transfer with progress tracking.

This module provides a QObject worker that handles file uploads and
downloads in background threads with real-time progress reporting.
"""

import os
import stat as stat_mod
import threading
import time
from datetime import datetime
from PyQt5.QtCore import pyqtSignal

from transfpro.core.sftp_manager import SFTPManager
from transfpro.config.constants import (
    TRANSFER_SPEED_UPDATE_INTERVAL, PROGRESS_EMIT_INTERVAL,
)
from transfpro.models.transfer import TransferTask, TransferDirection, TransferStatus
from .base_worker import BaseWorker


class TransferWorker(BaseWorker):
    """Background file transfer worker with progress tracking.

    Handles file uploads and downloads with real-time progress reporting.
    Supports pause/cancel operations and speed calculation.

    Signals:
        transfer_started: Emitted with transfer_id when transfer begins
        progress: Emitted with (transfer_id, bytes_done, bytes_total)
        transfer_completed: Emitted with (transfer_id, success)
        speed_updated: Emitted with (transfer_id, bytes_per_sec)
    """

    transfer_started = pyqtSignal(str)  # transfer_id
    progress = pyqtSignal(str, int, int)  # transfer_id, bytes_done, bytes_total
    transfer_completed = pyqtSignal(str, bool)  # transfer_id, success
    speed_updated = pyqtSignal(str, float)  # transfer_id, bytes_per_sec

    def __init__(self, sftp_manager: SFTPManager, transfer_task: TransferTask):
        """Initialize the file transfer worker.

        Args:
            sftp_manager: SFTPManager instance to use for file operations
            transfer_task: TransferTask object describing the transfer
        """
        super().__init__()
        self.sftp_manager = sftp_manager
        self.transfer_task = transfer_task
        self._pause_event = threading.Event()
        self._pause_event.set()  # starts in "running" (not paused) state
        self._last_progress_time = time.time()
        self._last_progress_bytes = 0
        self._last_progress_emit_time = 0.0
        self._chunk_counter = 0
        self._dedicated_sftp = None  # dedicated SFTP session for thread safety

    def cancel(self):
        """Cancel the transfer, waking it first if paused."""
        self._pause_event.set()  # unblock if paused so worker can exit
        super().cancel()

    def pause(self):
        """Pause the transfer — blocks the worker thread until resumed."""
        self._pause_event.clear()
        self.logger.debug(f"Transfer {self.transfer_task.id} paused")

    def resume(self):
        """Resume a paused transfer."""
        self._last_progress_time = time.time()
        self._last_progress_bytes = self.transfer_task.transferred_bytes
        self._pause_event.set()
        self.logger.debug(f"Transfer {self.transfer_task.id} resumed")

    def _progress_callback(self, bytes_transferred: int, bytes_total: int):
        """Handle progress updates from SFTP operations.

        Checks cancel/pause every 16 chunks (~1 MB) to minimize overhead
        while keeping responsiveness.  Throttles signal emission to ~10 Hz.

        Args:
            bytes_transferred: Number of bytes transferred so far
            bytes_total: Total number of bytes to transfer

        Raises:
            InterruptedError: If the transfer was cancelled.
        """
        self._chunk_counter += 1
        is_final = bytes_transferred >= bytes_total

        # Only check cancel/pause every 16 chunks (~1 MB) or on final chunk
        if not is_final and (self._chunk_counter & 0xF):
            self.transfer_task.transferred_bytes = bytes_transferred
            return

        if self.is_cancelled:
            raise InterruptedError("Transfer cancelled by user")

        # Block here while paused (instead of wasting bandwidth)
        if not self._pause_event.is_set():
            self._pause_event.wait()
            # Re-check cancel after waking from pause
            if self.is_cancelled:
                raise InterruptedError("Transfer cancelled by user")

        self.transfer_task.transferred_bytes = bytes_transferred

        # Throttle progress signal emission to PROGRESS_EMIT_INTERVAL
        current_time = time.time()
        time_since_emit = current_time - self._last_progress_emit_time

        if is_final or time_since_emit >= PROGRESS_EMIT_INTERVAL:
            self.progress.emit(self.transfer_task.id, bytes_transferred, bytes_total)
            self._last_progress_emit_time = current_time

        # Calculate transfer speed every second
        time_elapsed = current_time - self._last_progress_time

        if time_elapsed >= TRANSFER_SPEED_UPDATE_INTERVAL:
            bytes_transferred_since_last = bytes_transferred - self._last_progress_bytes
            speed_bps = bytes_transferred_since_last / time_elapsed if time_elapsed > 0 else 0

            self.transfer_task.speed_bps = speed_bps
            self.speed_updated.emit(self.transfer_task.id, speed_bps)

            self._last_progress_time = current_time
            self._last_progress_bytes = bytes_transferred

            self.logger.debug(
                f"Transfer {self.transfer_task.id}: "
                f"{bytes_transferred}/{bytes_total} bytes "
                f"({self.transfer_task.progress_percent:.1f}%) "
                f"at {speed_bps / 1024 / 1024:.2f} MB/s"
            )

    def do_work(self):
        """Execute the file transfer.

        Opens a dedicated SFTP session for thread-safe transfers,
        then performs the upload or download operation with progress tracking.
        """
        try:
            self.transfer_task.status = TransferStatus.IN_PROGRESS
            self.transfer_task.started_at = datetime.now()
            self.transfer_started.emit(self.transfer_task.id)

            self.status_message.emit(
                f"{'Uploading' if self.transfer_task.direction == TransferDirection.UPLOAD else 'Downloading'} "
                f"{self.transfer_task.local_path}..."
            )

            self.logger.info(
                f"Starting {self.transfer_task.direction.value} transfer: "
                f"{self.transfer_task.local_path} <-> {self.transfer_task.remote_path}"
            )

            # Open a dedicated SFTP session for this transfer (thread-safe)
            try:
                self._dedicated_sftp = self.sftp_manager.ssh.open_sftp()
            except Exception as e:
                self.logger.error(f"Failed to open dedicated SFTP session: {e}")
                raise

            # Initialize speed tracking
            self._last_progress_time = time.time()
            self._last_progress_bytes = 0

            success = False

            if self.transfer_task.direction == TransferDirection.UPLOAD:
                local = self.transfer_task.local_path
                remote = self.transfer_task.remote_path

                if os.path.isdir(local):
                    # ── Directory upload ──
                    success = self._upload_directory(local, remote)
                else:
                    success = self.sftp_manager.upload_file(
                        local_path=local,
                        remote_path=remote,
                        callback=self._progress_callback,
                        sftp_client=self._dedicated_sftp
                    )
            else:  # DOWNLOAD
                remote = self.transfer_task.remote_path
                local = self.transfer_task.local_path

                # Check if the remote path is a directory
                is_remote_dir = False
                try:
                    attr = self._dedicated_sftp.stat(remote)
                    is_remote_dir = stat_mod.S_ISDIR(attr.st_mode)
                except Exception:
                    pass

                if is_remote_dir:
                    # ── Directory download ──
                    success = self._download_directory(remote, local)
                else:
                    success = self.sftp_manager.download_file(
                        remote_path=remote,
                        local_path=local,
                        callback=self._progress_callback,
                        sftp_client=self._dedicated_sftp
                    )

            if self.is_cancelled:
                self.logger.info(f"Transfer {self.transfer_task.id} cancelled")
                self.transfer_task.status = TransferStatus.CANCELLED
                self._cleanup_partial_transfer()
                self.transfer_completed.emit(self.transfer_task.id, False)
                return

            if success:
                self.transfer_task.status = TransferStatus.COMPLETED
                self.transfer_task.completed_at = datetime.now()
                self.transfer_task.transferred_bytes = self.transfer_task.total_bytes

                # Final progress update
                self.progress.emit(
                    self.transfer_task.id,
                    self.transfer_task.total_bytes,
                    self.transfer_task.total_bytes
                )

                # Calculate final speed
                if self.transfer_task.started_at and self.transfer_task.completed_at:
                    duration = (
                        self.transfer_task.completed_at - self.transfer_task.started_at
                    ).total_seconds()
                    if duration > 0:
                        final_speed = self.transfer_task.total_bytes / duration
                        self.transfer_task.speed_bps = final_speed

                self.logger.info(
                    f"Transfer {self.transfer_task.id} completed successfully "
                    f"({self.transfer_task.total_bytes} bytes)"
                )
                self.status_message.emit(
                    f"Transfer completed: {self.transfer_task.local_path}"
                )
                self.transfer_completed.emit(self.transfer_task.id, True)
            else:
                error_msg = "Transfer failed"
                self.transfer_task.status = TransferStatus.FAILED
                self.transfer_task.error_message = error_msg
                self.logger.error(error_msg)
                self.status_message.emit(error_msg)
                self.transfer_completed.emit(self.transfer_task.id, False)

        except InterruptedError:
            # Raised from _progress_callback when cancelled
            self.logger.info(f"Transfer {self.transfer_task.id} cancelled")
            self.transfer_task.status = TransferStatus.CANCELLED
            self._cleanup_partial_transfer()
            self.transfer_completed.emit(self.transfer_task.id, False)
        except Exception as e:
            error_msg = f"Transfer error: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.transfer_task.status = TransferStatus.FAILED
            self.transfer_task.error_message = error_msg
            self.status_message.emit(error_msg)
            self.transfer_completed.emit(self.transfer_task.id, False)
        finally:
            # Close the dedicated SFTP session
            if self._dedicated_sftp is not None:
                try:
                    self._dedicated_sftp.close()
                except Exception:
                    pass
                self._dedicated_sftp = None

    # ── Partial transfer cleanup ──

    def _cleanup_partial_transfer(self):
        """Remove incomplete files left behind by a cancelled or failed transfer.

        For single-file uploads: removes the partially written remote file.
        For single-file downloads: removes the partially written local file.
        Directory transfers are skipped (too complex to safely reverse).
        """
        try:
            task = self.transfer_task

            if task.direction == TransferDirection.UPLOAD:
                # Skip directory uploads — can't safely reverse partial tree
                if os.path.isdir(task.local_path):
                    self.logger.debug(
                        "Skipping cleanup for directory upload"
                    )
                    return
                # Remove partial remote file
                if self._dedicated_sftp and task.remote_path:
                    try:
                        self._dedicated_sftp.remove(task.remote_path)
                        self.logger.info(
                            f"Cleaned up partial remote file: {task.remote_path}"
                        )
                    except FileNotFoundError:
                        pass  # File was never created
                    except IOError:
                        pass  # SFTP session may already be closed
                    except Exception as e:
                        self.logger.warning(
                            f"Could not clean up partial remote file "
                            f"{task.remote_path}: {e}"
                        )
            else:
                # Remove partial local file (only for single-file downloads)
                local = task.local_path
                if local and os.path.isfile(local):
                    try:
                        file_size = os.path.getsize(local)
                        # Only remove if it looks incomplete
                        if file_size < task.total_bytes:
                            os.remove(local)
                            self.logger.info(
                                f"Cleaned up partial local file: {local}"
                            )
                    except Exception as e:
                        self.logger.warning(
                            f"Could not clean up partial local file {local}: {e}"
                        )
        except Exception as e:
            self.logger.debug(f"Cleanup error (non-fatal): {e}")

    # ── Directory transfer helpers ──

    def _ssh_mkdir_p(self, paths: list):
        """Create remote directories via a single SSH `mkdir -p` command.

        Falls back to per-directory SFTP mkdir if the SSH command fails
        (e.g. restricted shells that don't support mkdir -p).
        """
        import shlex
        if not paths:
            return
        quoted = ' '.join(shlex.quote(p) for p in paths)
        try:
            _, stderr, code = self.sftp_manager.ssh.execute_command(
                f"mkdir -p {quoted}", timeout=30
            )
            if code == 0:
                return  # All directories created in one round-trip
            self.logger.warning(
                f"SSH mkdir -p returned {code}: {stderr.strip()}"
            )
        except Exception as e:
            self.logger.warning(f"SSH mkdir -p failed, using SFTP fallback: {e}")

        # Fallback: create directories one-by-one via SFTP
        sftp = self._dedicated_sftp
        for rdir in paths:
            try:
                sftp.mkdir(rdir)
            except IOError:
                try:
                    sftp.stat(rdir)  # Already exists
                except FileNotFoundError:
                    raise

    def _upload_directory(self, local_dir: str, remote_dir: str) -> bool:
        """Recursively upload a directory with progress tracking.

        Creates the remote directory structure in one SSH round-trip,
        then uploads files with pipelined writes and progress tracking.
        """
        sftp = self._dedicated_sftp

        # Walk local tree: collect dirs and files
        # followlinks=True so symlinked directories (e.g. GROMACS .ff) are traversed
        dir_list = [remote_dir]
        file_list = []  # [(local, remote, size)]
        total_bytes = 0

        for root, dirs, files in os.walk(local_dir, followlinks=True):
            for d in dirs:
                rel = os.path.relpath(os.path.join(root, d), local_dir)
                dir_list.append(f"{remote_dir}/{rel}".replace(os.sep, "/"))
            for f in files:
                local_file = os.path.join(root, f)
                # Resolve symlinks so we can read the actual file
                real_file = os.path.realpath(local_file)
                if not os.path.isfile(real_file):
                    self.logger.warning(f"Skipping non-file: {local_file}")
                    continue
                rel = os.path.relpath(local_file, local_dir)
                remote_file = f"{remote_dir}/{rel}".replace(os.sep, "/")
                try:
                    size = os.path.getsize(real_file)
                except OSError:
                    self.logger.warning(f"Skipping inaccessible file: {local_file}")
                    continue
                file_list.append((real_file, remote_file, size))
                total_bytes += size

        self.logger.info(
            f"Directory upload: {len(dir_list)} dirs, {len(file_list)} files, "
            f"{total_bytes} bytes total"
        )

        # Update total_bytes on the task so progress bar scales correctly
        if total_bytes > 0:
            self.transfer_task.total_bytes = total_bytes

        # Create all remote directories in one SSH round-trip
        self._ssh_mkdir_p(sorted(dir_list))

        # Upload files
        bytes_done = 0
        from transfpro.config.constants import SFTP_MAX_READ_SIZE

        for local_file, remote_file, fsize in file_list:
            if self.is_cancelled:
                raise InterruptedError("Transfer cancelled by user")

            written = 0
            with open(local_file, 'rb') as lf:
                with sftp.open(remote_file, 'wb') as rf:
                    rf.set_pipelined(True)
                    while True:
                        chunk = lf.read(SFTP_MAX_READ_SIZE)
                        if not chunk:
                            break
                        rf.write(chunk)
                        written += len(chunk)
                        self._progress_callback(bytes_done + written, total_bytes)

            bytes_done += fsize
            self.logger.debug(f"Uploaded {remote_file}")

        return True

    def _download_directory(self, remote_dir: str, local_dir: str) -> bool:
        """Recursively download a directory with progress tracking.

        Walks the remote directory tree, creates local directories,
        then downloads all files one by one with progress updates.
        """
        sftp = self._dedicated_sftp
        os.makedirs(local_dir, exist_ok=True)

        # Collect remote tree
        file_list = []  # [(remote, local, size)]
        total_bytes = 0

        def _walk(rpath, lpath):
            nonlocal total_bytes
            for attr in sftp.listdir_attr(rpath):
                rentry = f"{rpath}/{attr.filename}"
                lentry = os.path.join(lpath, attr.filename)
                if stat_mod.S_ISDIR(attr.st_mode):
                    os.makedirs(lentry, exist_ok=True)
                    _walk(rentry, lentry)
                else:
                    file_list.append((rentry, lentry, attr.st_size))
                    total_bytes += attr.st_size

        _walk(remote_dir, local_dir)

        self.logger.info(
            f"Directory download: {len(file_list)} files, {total_bytes} bytes total"
        )

        if total_bytes > 0:
            self.transfer_task.total_bytes = total_bytes

        # Download files
        bytes_done = 0
        from transfpro.config.constants import SFTP_MAX_READ_SIZE

        for remote_file, local_file, fsize in file_list:
            if self.is_cancelled:
                raise InterruptedError("Transfer cancelled by user")

            os.makedirs(os.path.dirname(local_file) or ".", exist_ok=True)
            read_bytes = 0
            with sftp.open(remote_file, 'rb') as rf:
                rf.prefetch(fsize)
                with open(local_file, 'wb', buffering=1024 * 1024) as lf:
                    while True:
                        chunk = rf.read(SFTP_MAX_READ_SIZE)
                        if not chunk:
                            break
                        lf.write(chunk)
                        read_bytes += len(chunk)
                        self._progress_callback(bytes_done + read_bytes, total_bytes)

            bytes_done += fsize
            self.logger.debug(f"Downloaded {local_file}")

        return True
