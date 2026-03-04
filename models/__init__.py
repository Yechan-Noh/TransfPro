"""
TransfPro Models Package

This package provides data models for representing HPC cluster information,
connections, jobs, files, and transfers.
"""

from .connection import ConnectionProfile
from .job import JobState, JobInfo, SimulationProgress
from .file_item import FileType, FileMetadata
from .transfer import TransferDirection, TransferStatus, TransferTask

__all__ = [
    # Connection models
    'ConnectionProfile',
    # Job models
    'JobState',
    'JobInfo',
    'SimulationProgress',
    # File models
    'FileType',
    'FileMetadata',
    # Transfer models
    'TransferDirection',
    'TransferStatus',
    'TransferTask',
]
