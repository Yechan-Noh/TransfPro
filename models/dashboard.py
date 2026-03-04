"""
Dashboard and cluster information models for TransfPro.

This module defines data models for representing cluster information,
storage details, and dashboard metrics for system monitoring.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Dict, Any, Optional

from .job import SimulationProgress


@dataclass
class PartitionInfo:
    """
    Represents information about a cluster partition.

    Attributes:
        name: Name of the partition.
        state: Current state of the partition (e.g., "up", "down").
        total_nodes: Total number of nodes in the partition.
        available_nodes: Number of available (idle) nodes.
        total_cpus: Total number of CPUs in the partition.
        max_time: Maximum time limit for jobs (e.g., "7-00:00:00").
        default: Whether this is the default partition (default: False).
    """

    name: str
    state: str
    total_nodes: int
    available_nodes: int
    total_cpus: int
    max_time: str
    default: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the PartitionInfo to a dictionary representation.

        Returns:
            Dictionary containing all partition attributes.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PartitionInfo':
        """
        Create a PartitionInfo instance from a dictionary.

        Args:
            data: Dictionary containing partition attributes.

        Returns:
            A new PartitionInfo instance.
        """
        return cls(**data)


@dataclass
class ClusterInfo:
    """
    Represents overall information about an HPC cluster.

    Attributes:
        partitions: List of partition information objects.
        total_nodes: Total number of nodes in the cluster.
        total_cpus: Total number of CPUs in the cluster.
        total_gpus: Total number of GPUs in the cluster.
    """

    partitions: List[PartitionInfo]
    total_nodes: int
    total_cpus: int
    total_gpus: int

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the ClusterInfo to a dictionary representation.

        Returns:
            Dictionary containing all cluster attributes with nested
            partitions converted to dictionaries.
        """
        return {
            'partitions': [p.to_dict() for p in self.partitions],
            'total_nodes': self.total_nodes,
            'total_cpus': self.total_cpus,
            'total_gpus': self.total_gpus,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ClusterInfo':
        """
        Create a ClusterInfo instance from a dictionary.

        Args:
            data: Dictionary containing cluster attributes with partitions
                  as a list of partition dictionaries.

        Returns:
            A new ClusterInfo instance.
        """
        data_copy = data.copy()
        if 'partitions' in data_copy:
            data_copy['partitions'] = [
                PartitionInfo.from_dict(p) if isinstance(p, dict) else p
                for p in data_copy['partitions']
            ]
        return cls(**data_copy)


@dataclass
class StorageInfo:
    """
    Represents storage quota and usage information.

    Attributes:
        path: Path to the storage location.
        label: Human-readable label (e.g., "Home", "Scratch", "Project").
        used_bytes: Amount of storage used in bytes.
        quota_bytes: Total quota in bytes.
    """

    path: str
    label: str
    used_bytes: int
    quota_bytes: int

    @property
    def usage_percent(self) -> float:
        """
        Calculate storage usage percentage.

        Returns:
            Usage percentage (0-100). Returns 100 if quota is 0.
        """
        if self.quota_bytes == 0:
            return 100.0
        return (self.used_bytes / self.quota_bytes) * 100.0

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the StorageInfo to a dictionary representation.

        Returns:
            Dictionary containing all storage attributes.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StorageInfo':
        """
        Create a StorageInfo instance from a dictionary.

        Args:
            data: Dictionary containing storage attributes.

        Returns:
            A new StorageInfo instance.
        """
        return cls(**data)


@dataclass
class DashboardMetrics:
    """
    Represents aggregated metrics and statistics for the cluster dashboard.

    Attributes:
        jobs_running: Number of currently running jobs.
        jobs_pending: Number of pending (queued) jobs.
        jobs_completed: Number of completed jobs.
        jobs_failed: Number of failed jobs.
        total_cpu_available: Total available CPUs in the cluster.
        cpu_used: CPUs currently in use.
        memory_available_gb: Available memory in gigabytes.
        memory_used_gb: Used memory in gigabytes.
        storage_info: List of storage information objects.
        active_simulations: List of active simulation progress objects.
        job_history_daily: Daily job count history (date -> {state: count}).
        cpu_hours_daily: Daily CPU hours history (date -> hours).
        timestamp: Timestamp when metrics were collected.
    """

    jobs_running: int = 0
    jobs_pending: int = 0
    jobs_completed: int = 0
    jobs_failed: int = 0
    total_cpu_available: int = 0
    cpu_used: int = 0
    memory_available_gb: float = 0.0
    memory_used_gb: float = 0.0
    storage_info: List[StorageInfo] = field(default_factory=list)
    active_simulations: List[SimulationProgress] = field(default_factory=list)
    job_history_daily: Dict[str, Dict[str, int]] = field(default_factory=dict)
    cpu_hours_daily: Dict[str, float] = field(default_factory=dict)
    timestamp: Optional[datetime] = None

    def __post_init__(self) -> None:
        """Initialize default timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now()

    @property
    def cpu_usage_percent(self) -> float:
        """
        Calculate CPU usage percentage.

        Returns:
            CPU usage percentage (0-100). Returns 0 if no CPUs are available.
        """
        if self.total_cpu_available == 0:
            return 0.0
        return (self.cpu_used / self.total_cpu_available) * 100.0

    @property
    def memory_usage_percent(self) -> float:
        """
        Calculate memory usage percentage.

        Returns:
            Memory usage percentage (0-100). Returns 0 if no memory is available.
        """
        total_memory = self.memory_available_gb + self.memory_used_gb
        if total_memory == 0:
            return 0.0
        return (self.memory_used_gb / total_memory) * 100.0

    @property
    def total_jobs(self) -> int:
        """
        Calculate total number of jobs tracked.

        Returns:
            Sum of running, pending, completed, and failed jobs.
        """
        return (self.jobs_running + self.jobs_pending +
                self.jobs_completed + self.jobs_failed)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the DashboardMetrics to a dictionary representation.

        Returns:
            Dictionary containing all metrics with nested objects
            converted to dictionaries and datetime to ISO format.
        """
        data = {
            'jobs_running': self.jobs_running,
            'jobs_pending': self.jobs_pending,
            'jobs_completed': self.jobs_completed,
            'jobs_failed': self.jobs_failed,
            'total_cpu_available': self.total_cpu_available,
            'cpu_used': self.cpu_used,
            'memory_available_gb': self.memory_available_gb,
            'memory_used_gb': self.memory_used_gb,
            'storage_info': [s.to_dict() for s in self.storage_info],
            'active_simulations': [s.to_dict() for s in self.active_simulations],
            'job_history_daily': self.job_history_daily,
            'cpu_hours_daily': self.cpu_hours_daily,
        }

        if self.timestamp:
            data['timestamp'] = self.timestamp.isoformat()

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DashboardMetrics':
        """
        Create a DashboardMetrics instance from a dictionary.

        Args:
            data: Dictionary containing metrics attributes with nested objects
                  and datetime strings in ISO format.

        Returns:
            A new DashboardMetrics instance.
        """
        data_copy = data.copy()

        # Convert storage_info dictionaries to StorageInfo objects
        if 'storage_info' in data_copy:
            data_copy['storage_info'] = [
                StorageInfo.from_dict(s) if isinstance(s, dict) else s
                for s in data_copy['storage_info']
            ]

        # Convert active_simulations dictionaries to SimulationProgress objects
        if 'active_simulations' in data_copy:
            data_copy['active_simulations'] = [
                SimulationProgress.from_dict(s) if isinstance(s, dict) else s
                for s in data_copy['active_simulations']
            ]

        # Convert timestamp string to datetime
        if isinstance(data_copy.get('timestamp'), str):
            data_copy['timestamp'] = datetime.fromisoformat(data_copy['timestamp'])

        return cls(**data_copy)
