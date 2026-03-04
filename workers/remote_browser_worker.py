"""Persistent worker for asynchronous remote SFTP file browser operations.

Uses a single long-lived QThread with signal-driven dispatch so that
rapid directory browsing doesn't pay thread-creation overhead per click.
"""

import logging
import shlex
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

logger = logging.getLogger(__name__)


class RemoteBrowserWorker(QObject):
    """Persistent SFTP worker that lives on a single background QThread.

    Instead of creating/destroying a thread per operation, the owning
    FileBrowserPane keeps one QThread alive and dispatches operations
    via the ``request`` signal.  Results come back on dedicated signals.

    Usage:
        worker = RemoteBrowserWorker(sftp_manager)
        thread = QThread()
        worker.moveToThread(thread)
        thread.start()
        # later:
        worker.request.emit('list_dir', '/home/user', {})
    """

    # ── Dispatch signal (UI → worker thread) ──
    request = pyqtSignal(str, str, dict)  # operation, path, extra_kwargs

    # ── Result signals (worker thread → UI) ──
    listing_ready = pyqtSignal(str, list)   # path, [FileMetadata]
    home_ready = pyqtSignal(str)            # home path
    operation_done = pyqtSignal(str, dict)   # operation name, metadata
    file_info_ready = pyqtSignal(object)    # FileMetadata
    error = pyqtSignal(str)                 # error message

    def __init__(self, sftp_manager):
        super().__init__()
        self.sftp_manager = sftp_manager
        # Connect the dispatch signal to the handler
        self.request.connect(self._handle_request)

    # ── Internal ──

    def _is_connected(self) -> bool:
        ssh = getattr(self.sftp_manager, 'ssh', None)
        if ssh and hasattr(ssh, 'is_connected'):
            return ssh.is_connected()
        return True

    @pyqtSlot(str, str, dict)
    def _handle_request(self, operation: str, path: str, kwargs: dict):
        """Execute one SFTP operation (runs on the worker thread)."""
        if not self._is_connected():
            logger.debug(f"Skipping '{operation}' — not connected")
            return

        try:
            if operation == 'list_dir':
                items = self.sftp_manager.list_directory(path or '.')
                self.listing_ready.emit(path, items)

            elif operation == 'home':
                home_path = self.sftp_manager.get_home_directory()
                self.home_ready.emit(home_path)

            elif operation == 'mkdir':
                if self.sftp_manager.create_directory(path):
                    name = path.rstrip('/').rsplit('/', 1)[-1]
                    self.operation_done.emit('mkdir', {
                        'path': path, 'name': name, 'is_dir': True
                    })
                else:
                    self.error.emit(f"Failed to create directory: {path}")

            elif operation == 'rename':
                old_path = kwargs.get('old_path', '')
                new_path = kwargs.get('new_path', '')
                if self.sftp_manager.rename(old_path, new_path):
                    new_name = new_path.rstrip('/').rsplit('/', 1)[-1]
                    self.operation_done.emit('rename', {
                        'old_path': old_path, 'new_path': new_path,
                        'new_name': new_name,
                    })
                else:
                    self.error.emit(f"Failed to rename: {old_path}")

            elif operation == 'delete':
                is_dir = kwargs.get('is_dir', False)
                if is_dir:
                    ok = self.sftp_manager.delete_directory(path)
                else:
                    ok = self.sftp_manager.delete_file(path)
                if ok:
                    self.operation_done.emit('delete', {'path': path})
                else:
                    self.error.emit(f"Failed to delete: {path}")

            elif operation == 'copy':
                # Remote-to-remote copy via SSH cp command
                src_paths = kwargs.get('src_paths', [])
                dest_dir = kwargs.get('dest_dir', '')
                if not src_paths or not dest_dir:
                    self.error.emit("Copy: missing source or destination")
                    return
                ssh = self.sftp_manager.ssh
                failed = []
                for src in src_paths:
                    dst = f"{dest_dir.rstrip('/')}/{src.rstrip('/').rsplit('/', 1)[-1]}"
                    # Skip copy-to-same-location
                    if src.rstrip('/') == dst.rstrip('/'):
                        continue
                    cmd = f"cp -r {shlex.quote(src)} {shlex.quote(dst)}"
                    _, stderr, exit_code = ssh.execute_command(cmd, timeout=120)
                    if exit_code != 0:
                        failed.append(f"{src}: {stderr.strip()}")
                        logger.error(f"Remote copy failed: {cmd} → {stderr}")
                if failed:
                    self.error.emit(
                        f"Copy failed for {len(failed)} item(s):\n"
                        + "\n".join(failed[:5])
                    )
                else:
                    self.operation_done.emit('copy', {})

            elif operation == 'info':
                metadata = self.sftp_manager.get_file_info(path)
                self.file_info_ready.emit(metadata)

            else:
                self.error.emit(f"Unknown operation: {operation}")

        except Exception as e:
            logger.error(f"Remote op '{operation}' failed: {e}")
            self.error.emit(str(e))
