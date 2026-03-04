"""
File transfer models for TransfPro.

This module defines data models for representing file transfer operations,
including upload and download tasks with progress tracking.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
import uuid


class TransferDirection(Enum):
    """Enumeration of file transfer directions."""

    UPLOAD = "upload"
    DOWNLOAD = "download"


class TransferStatus(Enum):
    """Enumeration of file transfer status states."""

    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class TransferTask:
    """
    Represents a single file transfer operation.

    Attributes:
        id: Unique identifier (UUID) for the transfer task.
        direction: Direction of transfer (upload or download).
        local_path: Path to file on local system.
        remote_path: Path to file on remote system.
        total_bytes: Total size of file to transfer in bytes.
        transferred_bytes: Bytes transferred so far (default: 0).
        status: Current transfer status (default: QUEUED).
        speed_bps: Transfer speed in bytes per second (default: 0.0).
        error_message: Error message if transfer failed (default: empty).
        started_at: Timestamp when transfer started.
        completed_at: Timestamp when transfer completed.
    """

    direction: TransferDirection
    local_path: str
    remote_path: str
    total_bytes: int
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    transferred_bytes: int = 0
    status: TransferStatus = TransferStatus.QUEUED
    speed_bps: float = 0.0
    error_message: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def progress_percent(self) -> float:
        """
        Calculate the transfer progress percentage.

        Returns:
            Completion percentage (0-100). Returns 100 if total_bytes is 0.
        """
        if self.total_bytes == 0:
            return 100.0
        return (self.transferred_bytes / self.total_bytes) * 100.0

    @property
    def estimated_seconds_remaining(self) -> float:
        """
        Estimate remaining transfer time in seconds.

        Calculates based on current transfer speed. Returns 0 if speed is 0
        or transfer is complete.

        Returns:
            Estimated seconds until transfer completion.
        """
        if self.speed_bps <= 0:
            return 0.0

        bytes_remaining = self.total_bytes - self.transferred_bytes
        if bytes_remaining <= 0:
            return 0.0

        return bytes_remaining / self.speed_bps

    @property
    def is_active(self) -> bool:
        """
        Check if the transfer is currently active.

        Returns:
            True if transfer is queued or in progress, False otherwise.
        """
        return self.status in (TransferStatus.QUEUED, TransferStatus.IN_PROGRESS)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the TransferTask to a dictionary representation.

        Returns:
            Dictionary containing all transfer attributes with TransferDirection
            and TransferStatus enums and datetime objects converted to strings.
        """
        data = asdict(self)

        # Convert enums to strings
        if isinstance(data['direction'], TransferDirection):
            data['direction'] = data['direction'].value
        if isinstance(data['status'], TransferStatus):
            data['status'] = data['status'].value

        # Convert datetime objects to ISO format
        if data['started_at'] is not None and isinstance(data['started_at'], datetime):
            data['started_at'] = data['started_at'].isoformat()
        if data['completed_at'] is not None and isinstance(data['completed_at'], datetime):
            data['completed_at'] = data['completed_at'].isoformat()

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TransferTask':
        """
        Create a TransferTask instance from a dictionary.

        Args:
            data: Dictionary containing transfer attributes. TransferDirection
                  and TransferStatus values as strings and datetime strings in
                  ISO format are automatically converted.

        Returns:
            A new TransferTask instance.
        """
        data_copy = data.copy()

        # Convert direction string to TransferDirection enum
        if isinstance(data_copy.get('direction'), str):
            data_copy['direction'] = TransferDirection(data_copy['direction'])

        # Convert status string to TransferStatus enum
        if isinstance(data_copy.get('status'), str):
            data_copy['status'] = TransferStatus(data_copy['status'])

        # Convert ISO format datetime strings to datetime objects
        if isinstance(data_copy.get('started_at'), str):
            data_copy['started_at'] = datetime.fromisoformat(data_copy['started_at'])
        if isinstance(data_copy.get('completed_at'), str):
            data_copy['completed_at'] = datetime.fromisoformat(data_copy['completed_at'])

        return cls(**data_copy)
