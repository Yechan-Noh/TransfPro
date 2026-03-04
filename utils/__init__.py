"""TransfPro Utilities Package"""

from .logger import setup_logger, get_logger
from .exceptions import (
    TransfProException,
    SSHConnectionError,
    SSHAuthenticationError,
    SSH2FAError,
    SFTPError,
    SFTPTransferError,
    SLURMError,
    JobSubmissionError,
    DatabaseError,
    GromacsParseError,
)
from .formatters import (
    format_file_size,
    format_duration,
    format_timestamp,
    format_transfer_speed,
    truncate_path,
    format_slurm_time,
)
from .validators import (
    validate_hostname,
    validate_port,
    validate_path,
    validate_job_name,
    validate_time_limit,
)

# PyQt5-dependent imports (deferred to avoid import errors)
try:
    from .file_icons import (
        get_file_icon,
        get_file_icon_by_type,
        get_directory_icon,
        get_file_type_description,
        is_gromacs_file,
    )
    _HAS_PYQT = True
except ImportError:
    _HAS_PYQT = False
    get_file_icon = None
    get_file_icon_by_type = None
    get_directory_icon = None
    get_file_type_description = None
    is_gromacs_file = None

__all__ = [
    "setup_logger",
    "get_logger",
    "TransfProException",
    "SSHConnectionError",
    "SSHAuthenticationError",
    "SSH2FAError",
    "SFTPError",
    "SFTPTransferError",
    "SLURMError",
    "JobSubmissionError",
    "DatabaseError",
    "GromacsParseError",
    "format_file_size",
    "format_duration",
    "format_timestamp",
    "format_transfer_speed",
    "truncate_path",
    "format_slurm_time",
    "validate_hostname",
    "validate_port",
    "validate_path",
    "validate_job_name",
    "validate_time_limit",
    "get_file_icon",
    "get_file_icon_by_type",
    "get_directory_icon",
    "get_file_type_description",
    "is_gromacs_file",
]
