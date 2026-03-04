"""Handles SFTP file operations (upload, download, browse) with progress tracking."""

import logging
import os
from typing import List, Optional, Callable, Tuple
from dataclasses import dataclass
from datetime import datetime
import stat
from paramiko.sftp_client import SFTPClient
from paramiko.ssh_exception import SSHException

from transfpro.config.constants import (
    SFTP_MAX_READ_SIZE, SFTP_OPERATION_TIMEOUT,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FileMetadata:
    """Metadata about a single remote file or directory."""
    name: str
    path: str
    size: int
    modified: datetime
    is_dir: bool
    permissions: int
    owner: str = ""
    group: str = ""
    is_symlink: bool = False


class SFTPManager:
    """High-level SFTP wrapper that adds progress callbacks, recursive
    directory operations, and timeout management on top of Paramiko."""

    def __init__(self, ssh_manager):
        self.ssh = ssh_manager

    def _get_sftp_with_timeout(self, timeout: int = SFTP_OPERATION_TIMEOUT) -> SFTPClient:
        """Grab an SFTP client and set a per-operation timeout on the channel."""
        sftp = self.ssh.get_sftp()
        try:
            sftp.get_channel().settimeout(timeout)
        except (OSError, AttributeError):
            pass  # Not every channel supports settimeout — move on
        return sftp

    def list_directory(self, path: str) -> List[FileMetadata]:
        """List the contents of a remote directory, directories first."""
        try:
            sftp = self._get_sftp_with_timeout()
            logger.debug(f"Listing directory: {path}")

            entries = sftp.listdir_attr(path)
            metadata_list = []

            for attr in entries:
                try:
                    modified = datetime.fromtimestamp(attr.st_mtime)
                except (ValueError, OSError):
                    modified = datetime.now()

                full_path = os.path.join(path, attr.filename)
                is_link = stat.S_ISLNK(attr.st_mode)
                is_dir = stat.S_ISDIR(attr.st_mode)

                # Symlinks: skip the extra stat() round-trip per entry.
                # The UI will resolve symlinks on-demand when double-clicked.

                metadata = FileMetadata(
                    name=attr.filename,
                    path=full_path,
                    size=attr.st_size,
                    modified=modified,
                    is_dir=is_dir,
                    permissions=attr.st_mode & 0o777,
                    is_symlink=is_link
                )
                metadata_list.append(metadata)

            # Sort: directories first, then by name
            metadata_list.sort(key=lambda x: (not x.is_dir, x.name.lower()))

            logger.debug(f"Listed {len(metadata_list)} entries in {path}")
            return metadata_list

        except Exception as e:
            logger.error(f"Failed to list directory {path}: {e}")
            raise SSHException(f"Failed to list directory: {e}")

    def upload_file(
        self,
        local_path: str,
        remote_path: str,
        callback: Optional[Callable[[int, int], None]] = None,
        sftp_client: Optional[SFTPClient] = None
    ) -> bool:
        """Upload a single file with optional progress callback.

        Uses 64 KB writes (pipelined) for better throughput than Paramiko's
        default 8 KB buffer.
        """
        try:
            if not os.path.exists(local_path):
                raise FileNotFoundError(f"Local file not found: {local_path}")
            if os.path.isdir(local_path):
                raise IsADirectoryError(
                    f"Path is a directory: {local_path}"
                )

            file_size = os.path.getsize(local_path)
            sftp = sftp_client or self.ssh.get_sftp()

            logger.info(f"Uploading {local_path} -> {remote_path} ({file_size} bytes)")

            # Use manual chunked upload for larger buffer control
            bytes_written = 0
            with open(local_path, 'rb') as local_f:
                with sftp.open(remote_path, 'wb') as remote_f:
                    remote_f.set_pipelined(True)
                    while True:
                        chunk = local_f.read(SFTP_MAX_READ_SIZE)
                        if not chunk:
                            break
                        remote_f.write(chunk)
                        bytes_written += len(chunk)
                        if callback:
                            callback(bytes_written, file_size)

            logger.info(f"Successfully uploaded {remote_path}")
            return True

        except Exception as e:
            logger.error(f"Upload failed: {e}")
            raise SSHException(f"Upload failed: {e}")

    def download_file(
        self,
        remote_path: str,
        local_path: str,
        callback: Optional[Callable[[int, int], None]] = None,
        sftp_client: Optional[SFTPClient] = None
    ) -> bool:
        """Download a single file with optional progress callback.

        Uses prefetch() to pipeline reads, which makes a big difference on
        high-latency connections.
        """
        try:
            sftp = sftp_client or self.ssh.get_sftp()

            # Get file size
            try:
                file_stat = sftp.stat(remote_path)
                file_size = file_stat.st_size
            except Exception as e:
                logger.warning(f"Could not stat remote file: {e}")
                file_size = 0

            logger.info(f"Downloading {remote_path} -> {local_path} ({file_size} bytes)")

            # Ensure local directory exists
            os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)

            # Use prefetch for pipelined read-ahead (much faster on high-latency links)
            bytes_read = 0
            with sftp.open(remote_path, 'rb') as remote_f:
                remote_f.prefetch(file_size)
                with open(local_path, 'wb', buffering=1024 * 1024) as local_f:
                    while True:
                        chunk = remote_f.read(SFTP_MAX_READ_SIZE)
                        if not chunk:
                            break
                        local_f.write(chunk)
                        bytes_read += len(chunk)
                        if callback:
                            callback(bytes_read, file_size)

            logger.info(f"Successfully downloaded {local_path}")
            return True

        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise SSHException(f"Download failed: {e}")

    def create_directory(self, remote_path: str) -> bool:
        """Create a single remote directory (non-recursive)."""
        try:
            sftp = self._get_sftp_with_timeout()
            logger.info(f"Creating directory: {remote_path}")
            sftp.mkdir(remote_path)
            return True
        except Exception as e:
            logger.error(f"Failed to create directory: {e}")
            raise SSHException(f"Failed to create directory: {e}")

    def mkdir_p(self, remote_path: str, sftp_client: Optional[SFTPClient] = None):
        """Create a remote directory, creating parent directories as needed.

        Args:
            remote_path: Remote directory path to create.
            sftp_client: Optional pre-opened SFTP client. Uses shared session if None.

        Raises:
            SSHException: If directory creation fails.
        """
        # Normalise: strip trailing slashes, bail on root / empty
        remote_path = remote_path.rstrip('/')
        if not remote_path or remote_path == '.':
            return

        sftp = sftp_client or self._get_sftp_with_timeout()
        try:
            sftp.stat(remote_path)
            return  # Already exists
        except FileNotFoundError:
            pass
        # Recursively ensure parent exists
        parent = remote_path.rsplit('/', 1)[0]
        if parent and parent != remote_path:
            self.mkdir_p(parent, sftp_client=sftp)
        try:
            sftp.mkdir(remote_path)
        except IOError:
            # Race condition: another channel may have created it
            try:
                sftp.stat(remote_path)
            except FileNotFoundError:
                raise

    def walk_remote_tree(
        self, remote_path: str, sftp_client: Optional[SFTPClient] = None,
        max_depth: int = 50
    ) -> Tuple[List[str], List[Tuple[str, int]]]:
        """Walk a remote directory tree and return all dirs and files.

        Args:
            remote_path: Root remote directory path.
            sftp_client: Optional pre-opened SFTP client. Uses shared session if None.
            max_depth: Maximum recursion depth (default 50). Guards against symlink loops.

        Returns:
            Tuple of (dir_list, file_list) where:
                dir_list: sorted list of remote directory paths (parent-first)
                file_list: list of (remote_file_path, file_size) tuples

        Raises:
            SSHException: If the walk fails or exceeds max_depth.
        """
        sftp = sftp_client or self._get_sftp_with_timeout()
        dirs: List[str] = []
        files: List[Tuple[str, int]] = []

        def _walk(rpath: str, depth: int = 0):
            if depth > max_depth:
                raise SSHException(
                    f"Directory too deeply nested (>{max_depth} levels): {rpath}"
                )
            try:
                for attr in sftp.listdir_attr(rpath):
                    entry = f"{rpath}/{attr.filename}"
                    if stat.S_ISDIR(attr.st_mode):
                        dirs.append(entry)
                        _walk(entry, depth + 1)
                    else:
                        files.append((entry, attr.st_size))
            except SSHException:
                raise
            except Exception as e:
                logger.error(f"Error walking remote directory {rpath}: {e}")
                raise SSHException(f"Failed to walk remote directory: {e}")

        _walk(remote_path)
        dirs.sort()  # Parent-first for safe directory creation
        return dirs, files

    def delete_file(self, remote_path: str) -> bool:
        """Delete a single remote file."""
        try:
            sftp = self._get_sftp_with_timeout()
            logger.info(f"Deleting file: {remote_path}")
            sftp.remove(remote_path)
            return True
        except Exception as e:
            logger.error(f"Failed to delete file: {e}")
            raise SSHException(f"Failed to delete file: {e}")

    def delete_directory(self, remote_path: str) -> bool:
        """Recursively delete a remote directory and all its contents."""
        try:
            sftp = self._get_sftp_with_timeout()
            logger.info(f"Deleting directory: {remote_path}")

            def _recursive_delete(path: str, depth: int = 0):
                """Recursively delete directory structure."""
                if depth > 50:
                    raise SSHException(f"Directory too deeply nested (>{depth} levels): {path}")
                entries = sftp.listdir_attr(path)
                for attr in entries:
                    entry_path = f"{path}/{attr.filename}"
                    if stat.S_ISDIR(attr.st_mode):
                        _recursive_delete(entry_path, depth + 1)
                    else:
                        sftp.remove(entry_path)
                sftp.rmdir(path)

            _recursive_delete(remote_path)
            return True

        except Exception as e:
            logger.error(f"Failed to delete directory: {e}")
            raise SSHException(f"Failed to delete directory: {e}")

    def rename(self, old_path: str, new_path: str) -> bool:
        """Rename or move a remote file/directory."""
        try:
            sftp = self._get_sftp_with_timeout()
            logger.info(f"Renaming {old_path} -> {new_path}")
            sftp.rename(old_path, new_path)
            return True
        except Exception as e:
            logger.error(f"Failed to rename: {e}")
            raise SSHException(f"Failed to rename: {e}")

    def get_file_info(self, remote_path: str) -> FileMetadata:
        """Get metadata (size, permissions, etc.) for a remote path."""
        try:
            sftp = self._get_sftp_with_timeout()
            attr = sftp.stat(remote_path)

            try:
                modified = datetime.fromtimestamp(attr.st_mtime)
            except (ValueError, OSError):
                modified = datetime.now()

            return FileMetadata(
                name=os.path.basename(remote_path),
                path=remote_path,
                size=attr.st_size,
                modified=modified,
                is_dir=stat.S_ISDIR(attr.st_mode),
                permissions=attr.st_mode & 0o777
            )

        except Exception as e:
            logger.error(f"Failed to get file info: {e}")
            raise SSHException(f"Failed to get file info: {e}")

    def exists(self, remote_path: str) -> bool:
        """Check whether a remote path exists."""
        try:
            sftp = self._get_sftp_with_timeout()
            sftp.stat(remote_path)
            return True
        except FileNotFoundError:
            return False
        except Exception as e:
            logger.error(f"Failed to check existence: {e}")
            raise SSHException(f"Failed to check existence: {e}")

    def get_home_directory(self) -> str:
        """Return the remote user's home directory path."""
        try:
            sftp = self._get_sftp_with_timeout()
            home = sftp.normalize(".")
            logger.debug(f"Home directory: {home}")
            return home
        except Exception as e:
            logger.error(f"Failed to get home directory: {e}")
            raise SSHException(f"Failed to get home directory: {e}")

    def read_text_file(self, remote_path: str, max_lines: int = 1000) -> str:
        """Read a remote text file (up to *max_lines* lines). Handy for log viewing."""
        try:
            sftp = self._get_sftp_with_timeout()
            logger.debug(f"Reading text file: {remote_path}")

            with sftp.open(remote_path, 'r') as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        lines.append(f"\n... (truncated after {max_lines} lines)")
                        break
                    lines.append(line.rstrip('\n\r'))

            content = '\n'.join(lines)
            logger.debug(f"Read {len(lines)} lines from {remote_path}")
            return content

        except Exception as e:
            logger.error(f"Failed to read file: {e}")
            raise SSHException(f"Failed to read file: {e}")

    def tail_file(self, remote_path: str, lines: int = 100) -> str:
        """Return the last *lines* lines of a remote file.

        Reads progressively larger chunks from the end of the file so we
        never need to transfer the whole thing.
        """
        try:
            sftp = self._get_sftp_with_timeout()
            logger.debug(f"Tailing file: {remote_path} (last {lines} lines)")

            file_stat = sftp.stat(remote_path)
            file_size = file_stat.st_size

            if file_size == 0:
                return ""

            # Reverse-seek: read progressively larger chunks from the end
            # Start with a reasonable guess (avg 120 bytes/line)
            chunk_size = min(lines * 120, file_size)
            data = b""

            with sftp.open(remote_path, 'rb') as f:
                while True:
                    offset = max(0, file_size - chunk_size)
                    f.seek(offset)
                    data = f.read(file_size - offset)

                    # Count newlines; we need lines+1 to get `lines` complete lines
                    if data.count(b'\n') >= lines + 1 or offset == 0:
                        break
                    # Double chunk size for next attempt
                    chunk_size = min(chunk_size * 2, file_size)

            # Split and take last N lines
            all_lines = data.decode('utf-8', errors='replace').splitlines(True)
            tail_lines = all_lines[-lines:]
            content = ''.join(tail_lines)

            logger.debug(f"Retrieved {len(tail_lines)} lines from {remote_path}")
            return content

        except Exception as e:
            logger.error(f"Failed to tail file: {e}")
            raise SSHException(f"Failed to tail file: {e}")
