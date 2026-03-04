"""
TransfPro Custom Exceptions

This module defines a custom exception hierarchy for TransfPro application,
organized by functional areas (SSH, SFTP, SLURM, Database, GROMACS).
"""


class TransfProException(Exception):
    """
    Base exception class for all TransfPro exceptions.

    All custom exceptions in the application should inherit from this class
    to allow for unified exception handling.
    """

    def __init__(self, message: str, error_code: int = 1) -> None:
        """
        Initialize the exception.

        Args:
            message: Error message describing the exception
            error_code: Numeric error code for classification
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code

    def __str__(self) -> str:
        """Return string representation of the exception."""
        return f"{self.__class__.__name__}: {self.message}"


# SSH Exceptions


class SSHConnectionError(TransfProException):
    """
    Raised when an SSH connection cannot be established.

    This includes network timeouts, connection refused, and host unreachable.
    """

    def __init__(self, message: str, hostname: str = "", port: int = 22) -> None:
        """
        Initialize SSH connection error.

        Args:
            message: Error message
            hostname: Hostname that failed to connect
            port: SSH port that was attempted
        """
        super().__init__(message, error_code=1001)
        self.hostname = hostname
        self.port = port


class SSHAuthenticationError(TransfProException):
    """
    Raised when SSH authentication fails.

    This includes password authentication failures and key authentication issues.
    """

    def __init__(
        self,
        message: str,
        auth_method: str = "password",
        username: str = "",
    ) -> None:
        """
        Initialize SSH authentication error.

        Args:
            message: Error message
            auth_method: Authentication method that failed (password, key, etc.)
            username: Username that failed to authenticate
        """
        super().__init__(message, error_code=1002)
        self.auth_method = auth_method
        self.username = username


class SSH2FAError(TransfProException):
    """
    Raised when two-factor authentication (2FA) is required but not provided.

    This includes scenarios where 2FA code is invalid or timeout.
    """

    def __init__(self, message: str, max_attempts: int = 3) -> None:
        """
        Initialize 2FA error.

        Args:
            message: Error message
            max_attempts: Maximum number of 2FA attempts allowed
        """
        super().__init__(message, error_code=1003)
        self.max_attempts = max_attempts


# SFTP Exceptions


class SFTPError(TransfProException):
    """
    Base exception for SFTP-related errors.

    This includes permission denied, file not found, and other SFTP protocol errors.
    """

    def __init__(self, message: str, sftp_error_code: int = 0) -> None:
        """
        Initialize SFTP error.

        Args:
            message: Error message
            sftp_error_code: SFTP protocol error code
        """
        super().__init__(message, error_code=2001)
        self.sftp_error_code = sftp_error_code


class SFTPTransferError(SFTPError):
    """
    Raised when file transfer fails.

    This includes incomplete transfers, checksum mismatches, and disk space issues.
    """

    def __init__(
        self,
        message: str,
        local_path: str = "",
        remote_path: str = "",
        bytes_transferred: int = 0,
    ) -> None:
        """
        Initialize SFTP transfer error.

        Args:
            message: Error message
            local_path: Local file path involved in transfer
            remote_path: Remote file path involved in transfer
            bytes_transferred: Number of bytes transferred before failure
        """
        super().__init__(message, sftp_error_code=2002)
        self.error_code = 2002
        self.local_path = local_path
        self.remote_path = remote_path
        self.bytes_transferred = bytes_transferred


# SLURM Exceptions


class SLURMError(TransfProException):
    """
    Base exception for SLURM-related errors.

    This includes job submission failures, job status query errors, and SLURM command failures.
    """

    def __init__(self, message: str, slurm_error_code: int = 0) -> None:
        """
        Initialize SLURM error.

        Args:
            message: Error message
            slurm_error_code: SLURM error code from the system
        """
        super().__init__(message, error_code=3001)
        self.slurm_error_code = slurm_error_code


class JobSubmissionError(SLURMError):
    """
    Raised when a job submission to SLURM fails.

    This includes script errors, invalid parameters, and resource unavailability.
    """

    def __init__(
        self,
        message: str,
        job_name: str = "",
        partition: str = "",
        reason: str = "",
    ) -> None:
        """
        Initialize job submission error.

        Args:
            message: Error message
            job_name: Name of the job that failed to submit
            partition: SLURM partition targeted for submission
            reason: Reason for submission failure from SLURM
        """
        super().__init__(message, slurm_error_code=3002)
        self.error_code = 3002
        self.job_name = job_name
        self.partition = partition
        self.reason = reason


class JobStatusError(SLURMError):
    """
    Raised when retrieving job status from SLURM fails.

    This includes job not found and SLURM query errors.
    """

    def __init__(self, message: str, job_id: str = "") -> None:
        """
        Initialize job status error.

        Args:
            message: Error message
            job_id: Job ID that status could not be retrieved for
        """
        super().__init__(message, slurm_error_code=3003)
        self.error_code = 3003
        self.job_id = job_id


class JobCancellationError(SLURMError):
    """
    Raised when job cancellation fails.

    This includes permission denied and job already finished.
    """

    def __init__(self, message: str, job_id: str = "") -> None:
        """
        Initialize job cancellation error.

        Args:
            message: Error message
            job_id: Job ID that could not be cancelled
        """
        super().__init__(message, slurm_error_code=3004)
        self.error_code = 3004
        self.job_id = job_id


# Database Exceptions


class DatabaseError(TransfProException):
    """
    Base exception for database-related errors.

    This includes connection failures, query errors, and transaction failures.
    """

    def __init__(self, message: str, operation: str = "") -> None:
        """
        Initialize database error.

        Args:
            message: Error message
            operation: Database operation that failed
        """
        super().__init__(message, error_code=4001)
        self.operation = operation


class DatabaseConnectionError(DatabaseError):
    """
    Raised when database connection cannot be established.

    This includes connection timeouts and invalid credentials.
    """

    def __init__(self, message: str, database_url: str = "") -> None:
        """
        Initialize database connection error.

        Args:
            message: Error message
            database_url: Database URL that failed to connect
        """
        super().__init__(message, operation="connect")
        self.error_code = 4002
        self.database_url = database_url


class DatabaseQueryError(DatabaseError):
    """
    Raised when a database query fails.

    This includes SQL syntax errors and constraint violations.
    """

    def __init__(self, message: str, query: str = "") -> None:
        """
        Initialize database query error.

        Args:
            message: Error message
            query: SQL query that failed
        """
        super().__init__(message, operation="query")
        self.error_code = 4003
        self.query = query


class DatabaseIntegrityError(DatabaseError):
    """
    Raised when database integrity constraint is violated.

    This includes duplicate keys, foreign key violations, etc.
    """

    def __init__(self, message: str, constraint: str = "") -> None:
        """
        Initialize database integrity error.

        Args:
            message: Error message
            constraint: Constraint that was violated
        """
        super().__init__(message, operation="integrity")
        self.error_code = 4004
        self.constraint = constraint


# GROMACS Exceptions


class GromacsParseError(TransfProException):
    """
    Raised when parsing GROMACS files or output fails.

    This includes malformed structure files, topology errors, and invalid parameters.
    """

    def __init__(
        self,
        message: str,
        file_path: str = "",
        file_type: str = "",
    ) -> None:
        """
        Initialize GROMACS parse error.

        Args:
            message: Error message
            file_path: Path to the file that failed to parse
            file_type: Type of GROMACS file (.gro, .top, .mdp, etc.)
        """
        super().__init__(message, error_code=5001)
        self.file_path = file_path
        self.file_type = file_type


class GromacsExecutionError(TransfProException):
    """
    Raised when GROMACS command execution fails.

    This includes missing GROMACS installation and command failures.
    """

    def __init__(self, message: str, command: str = "", return_code: int = 0) -> None:
        """
        Initialize GROMACS execution error.

        Args:
            message: Error message
            command: GROMACS command that failed
            return_code: Return code from the GROMACS command
        """
        super().__init__(message, error_code=5002)
        self.command = command
        self.return_code = return_code


# Configuration Exceptions


class ConfigurationError(TransfProException):
    """
    Raised when application configuration is invalid.

    This includes missing required settings and invalid parameter values.
    """

    def __init__(self, message: str, config_key: str = "") -> None:
        """
        Initialize configuration error.

        Args:
            message: Error message
            config_key: Configuration key that is invalid
        """
        super().__init__(message, error_code=6001)
        self.config_key = config_key


# Validation Exceptions


class ValidationError(TransfProException):
    """
    Raised when input validation fails.

    This includes invalid hostnames, ports, paths, and job parameters.
    """

    def __init__(self, message: str, field: str = "", value: str = "") -> None:
        """
        Initialize validation error.

        Args:
            message: Error message
            field: Field name that failed validation
            value: Value that failed validation
        """
        super().__init__(message, error_code=7001)
        self.field = field
        self.value = value
