"""Application-wide constants — metadata, timeouts, transfer settings,
SLURM defaults, and UI colour schemes. All in one place."""

from typing import Dict, Set

# Application Metadata
APP_NAME: str = "TransfPro"
APP_VERSION: str = "1.0.0"
APP_DESCRIPTION: str = "Secure File Transfer & Remote Server Management"
APP_AUTHOR: str = "TransfPro Team"
APP_LICENSE: str = "MIT"

# SSH Configuration
SSH_DEFAULT_TIMEOUT: int = 10  # seconds
SSH_DEFAULT_PORT: int = 22
SSH_KEEPALIVE_INTERVAL: int = 60  # seconds

# Refresh and Update Intervals
DEFAULT_REFRESH_INTERVAL: int = 30  # seconds
DASHBOARD_REFRESH_INTERVAL: int = 5  # seconds
FILE_LIST_REFRESH_INTERVAL: int = 10  # seconds
JOB_STATUS_REFRESH_INTERVAL: int = 15  # seconds

# Logging Configuration
DEFAULT_JOB_LOG_LINES: int = 100
MAX_LOG_ENTRIES: int = 10000

# Two-Factor Authentication
TWO_FA_TIMEOUT: int = 60  # seconds
TWO_FA_MAX_ATTEMPTS: int = 3

# File Transfer Configuration
MAX_CONCURRENT_TRANSFERS: int = 4
TRANSFER_CHUNK_SIZE: int = 65536  # 64 KB chunks
TRANSFER_TIMEOUT: int = 300  # seconds

# SFTP Performance Tuning
# Paramiko defaults are tiny (64KB window, 32KB packet) — increase for throughput
SFTP_WINDOW_SIZE: int = 2 * 1024 * 1024      # 2 MB sliding window per channel
SFTP_MAX_PACKET_SIZE: int = 64 * 1024         # 64 KB max packet (safe upper bound)
SFTP_MAX_READ_SIZE: int = 64 * 1024           # 64 KB read request size for prefetch
SFTP_OPERATION_TIMEOUT: int = 30              # Per-operation channel timeout (seconds)

# Transfer speed update interval
TRANSFER_SPEED_UPDATE_INTERVAL: float = 1.0   # Seconds between speed recalculations
PROGRESS_EMIT_INTERVAL: float = 0.1           # Min seconds between progress signal emissions

# SLURM Default Settings
SLURM_DEFAULT_PARTITION: str = "compute"
SLURM_DEFAULT_TIME_LIMIT: int = 60  # minutes
SLURM_DEFAULT_CPUS: int = 4
SLURM_DEFAULT_MEMORY: str = "4G"
SLURM_DEFAULT_NODES: int = 1
SLURM_JOB_POLL_INTERVAL: int = 5  # seconds

# SLURM Job States (subset)
SLURM_JOB_STATES: Set[str] = {
    "RUNNING",
    "PENDING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "TIMEOUT",
    "NODE_FAIL",
    "PREEMPTED",
    "BOOT_FAIL",
    "DEADLINE",
    "OUT_OF_MEMORY",
}

# Job Status Color Scheme
JOB_STATUS_COLORS: Dict[str, str] = {
    "Running": "#4CAF50",      # Green
    "Pending": "#FF9800",      # Orange
    "Completed": "#2196F3",    # Blue
    "Failed": "#F44336",       # Red
    "Cancelled": "#9E9E9E",    # Grey
    "Timeout": "#F44336",      # Red
    "Unknown": "#757575",      # Dark Grey
    "Paused": "#FFC107",       # Amber
    "Suspended": "#9C27B0",    # Purple
    "Preempted": "#FF5722",    # Deep Orange
}

# Transfer Status Constants
TRANSFER_STATUS_PENDING: str = "pending"
TRANSFER_STATUS_IN_PROGRESS: str = "in_progress"
TRANSFER_STATUS_COMPLETED: str = "completed"
TRANSFER_STATUS_FAILED: str = "failed"
TRANSFER_STATUS_CANCELLED: str = "cancelled"

TRANSFER_STATUSES: Set[str] = {
    TRANSFER_STATUS_PENDING,
    TRANSFER_STATUS_IN_PROGRESS,
    TRANSFER_STATUS_COMPLETED,
    TRANSFER_STATUS_FAILED,
    TRANSFER_STATUS_CANCELLED,
}

# Database Configuration
DATABASE_TIMEOUT: int = 30  # seconds
DATABASE_MAX_RETRIES: int = 3

# UI Configuration
DEFAULT_WINDOW_WIDTH: int = 1200
DEFAULT_WINDOW_HEIGHT: int = 800
MIN_WINDOW_WIDTH: int = 800
MIN_WINDOW_HEIGHT: int = 600

# Table Configuration
ROWS_PER_PAGE: int = 50
MAX_TABLE_ROWS: int = 1000

# Pagination
DEFAULT_PAGE_SIZE: int = 20
MAX_PAGE_SIZE: int = 100

# Path Configuration
HOME_DIR_PLACEHOLDER: str = "~"
