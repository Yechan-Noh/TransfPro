"""
Job information models for TransfPro.

This module defines data models for representing HPC job information,
including SLURM job states and simulation progress tracking.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any


class JobState(Enum):
    """Enumeration of possible HPC job states."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    NODE_FAIL = "NODE_FAIL"
    UNKNOWN = "UNKNOWN"


@dataclass(slots=True)
class JobInfo:
    """
    Represents information about a submitted HPC job.

    Attributes:
        job_id: Unique job identifier assigned by the scheduler.
        name: Job name as submitted.
        state: Current state of the job.
        user: Username of the job owner.
        partition: Cluster partition the job runs on.
        nodes: Number of allocated nodes.
        cpus: Total number of allocated CPUs.
        mem_per_node: Memory allocated per node (e.g., "128G").
        time_limit: Maximum time limit in HH:MM:SS format.
        time_used: Time consumed so far in HH:MM:SS format.
        submit_time: Timestamp when job was submitted.
        start_time: Timestamp when job started running.
        end_time: Timestamp when job finished.
        work_dir: Working directory on remote system (default: empty).
        output_file: Path to stdout file (default: empty).
        error_file: Path to stderr file (default: empty).
        command: Original command or script executed (default: empty).
        account: Account/project used for billing (default: empty).
        tpr_file: Path to GROMACS TPR file (optional).
        log_file: Path to GROMACS log file (optional).
        progress_percent: Job completion percentage (default: 0.0).
        ns_per_day: Nanoseconds per day (GROMACS performance metric).
        estimated_completion: Estimated completion timestamp.
        current_step: Current simulation step (default: 0).
        total_steps: Total simulation steps (default: 0).
        current_time_ps: Current simulation time in picoseconds (default: 0.0).
        total_time_ps: Total simulation time in picoseconds (default: 0.0).
    """

    job_id: str
    name: str
    state: JobState
    user: str
    partition: str
    nodes: int
    cpus: int
    mem_per_node: str
    time_limit: str
    time_used: str
    submit_time: Optional[datetime]
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    work_dir: str = ""
    output_file: str = ""
    error_file: str = ""
    command: str = ""
    account: str = ""
    tpr_file: Optional[str] = None
    log_file: Optional[str] = None
    progress_percent: float = 0.0
    ns_per_day: float = 0.0
    estimated_completion: Optional[datetime] = None
    current_step: int = 0
    total_steps: int = 0
    current_time_ps: float = 0.0
    total_time_ps: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the JobInfo to a dictionary representation.

        Returns:
            Dictionary containing all job attributes with datetime objects
            and JobState enums converted to ISO format strings and string values.
        """
        data = asdict(self)

        # Convert JobState enum to string
        if isinstance(data['state'], JobState):
            data['state'] = data['state'].value

        # Convert datetime objects to ISO format
        for key in ['submit_time', 'start_time', 'end_time', 'estimated_completion']:
            if data[key] is not None and isinstance(data[key], datetime):
                data[key] = data[key].isoformat()

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'JobInfo':
        """
        Create a JobInfo instance from a dictionary.

        Args:
            data: Dictionary containing job attributes. JobState values as strings
                  and datetime strings in ISO format are automatically converted.

        Returns:
            A new JobInfo instance.
        """
        data_copy = data.copy()

        # Convert state string to JobState enum
        if isinstance(data_copy.get('state'), str):
            data_copy['state'] = JobState(data_copy['state'])

        # Convert ISO format datetime strings to datetime objects
        for key in ['submit_time', 'start_time', 'end_time', 'estimated_completion']:
            if isinstance(data_copy.get(key), str):
                data_copy[key] = datetime.fromisoformat(data_copy[key])

        return cls(**data_copy)

    def is_active(self) -> bool:
        """
        Check if the job is currently active (running or pending).

        Returns:
            True if the job is in PENDING or RUNNING state, False otherwise.
        """
        return self.state in (JobState.PENDING, JobState.RUNNING)

    def is_gromacs_job(self) -> bool:
        """
        Check if this job is a GROMACS simulation based on file presence.

        Returns:
            True if TPR file or log file is specified, False otherwise.
        """
        return bool(self.tpr_file or self.log_file)


@dataclass(slots=True)
class SimulationProgress:
    """
    Represents progress information for a running molecular dynamics simulation.

    Attributes:
        job_id: Associated job identifier.
        job_name: Name of the simulation job.
        current_time_ps: Current simulation time in picoseconds.
        total_time_ps: Total simulation time in picoseconds.
        ns_per_day: Performance metric - nanoseconds per day.
        percent_complete: Completion percentage (0-100).
        estimated_hours_remaining: Estimated time to completion in hours.
        current_step: Current simulation step.
        total_steps: Total simulation steps.
        wall_time_used: Wall clock time used in HH:MM:SS format.
    """

    job_id: str
    job_name: str
    current_time_ps: float
    total_time_ps: float
    ns_per_day: float
    percent_complete: float
    estimated_hours_remaining: float
    current_step: int
    total_steps: int
    wall_time_used: str

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the SimulationProgress to a dictionary representation.

        Returns:
            Dictionary containing all progress attributes.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SimulationProgress':
        """
        Create a SimulationProgress instance from a dictionary.

        Args:
            data: Dictionary containing progress attributes.

        Returns:
            A new SimulationProgress instance.
        """
        return cls(**data)
