"""
TransfPro Formatting Utilities

This module provides helper functions for formatting various data types into
human-readable strings, including file sizes, durations, timestamps, and paths.
"""

from datetime import datetime
from typing import Optional

# Module-level constants for unit tuples
_SIZE_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")
_SPEED_UNITS = ("B/s", "KB/s", "MB/s", "GB/s", "TB/s")


def format_file_size(bytes_size: int) -> str:
    """
    Format bytes into a human-readable file size string.

    Converts bytes to the most appropriate unit (B, KB, MB, GB, TB).

    Args:
        bytes_size: Size in bytes

    Returns:
        str: Formatted file size string (e.g., "1.5 GB")

    Examples:
        >>> format_file_size(1024)
        '1.0 KB'
        >>> format_file_size(1536)
        '1.5 KB'
        >>> format_file_size(1073741824)
        '1.0 GB'
    """
    if bytes_size < 0:
        return "0 B"

    size = float(bytes_size)
    unit_index = 0

    while size >= 1024.0 and unit_index < len(_SIZE_UNITS) - 1:
        size /= 1024.0
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {_SIZE_UNITS[unit_index]}"

    return f"{size:.1f} {_SIZE_UNITS[unit_index]}"


def format_duration(seconds: int) -> str:
    """
    Format seconds into a human-readable duration string.

    Converts seconds to days, hours, minutes, and seconds format.

    Args:
        seconds: Duration in seconds

    Returns:
        str: Formatted duration string (e.g., "2h 35m 45s")

    Examples:
        >>> format_duration(60)
        '1m'
        >>> format_duration(3661)
        '1h 1m 1s'
        >>> format_duration(86400)
        '1d'
    """
    if seconds < 0:
        return "0s"

    if seconds == 0:
        return "0s"

    days = seconds // 86400
    remaining = seconds % 86400

    hours = remaining // 3600
    remaining = remaining % 3600

    minutes = remaining // 60
    secs = remaining % 60

    parts = []

    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts)


def format_timestamp(dt: Optional[datetime] = None, include_time: bool = True) -> str:
    """
    Format a datetime object into a human-readable timestamp string.

    Args:
        dt: datetime object to format (uses current time if None)
        include_time: Include time component if True, date only if False

    Returns:
        str: Formatted timestamp string (e.g., "2026-02-28 14:30:45")

    Examples:
        >>> dt = datetime(2026, 2, 28, 14, 30, 45)
        >>> format_timestamp(dt)
        '2026-02-28 14:30:45'
        >>> format_timestamp(dt, include_time=False)
        '2026-02-28'
    """
    if dt is None:
        dt = datetime.now()

    if include_time:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    else:
        return dt.strftime("%Y-%m-%d")


def format_transfer_speed(bytes_per_second: float) -> str:
    """
    Format transfer speed into a human-readable string.

    Converts bytes per second to the most appropriate unit (B/s, KB/s, MB/s, GB/s).

    Args:
        bytes_per_second: Transfer speed in bytes per second

    Returns:
        str: Formatted speed string (e.g., "15.2 MB/s")

    Examples:
        >>> format_transfer_speed(1024)
        '1.0 KB/s'
        >>> format_transfer_speed(15728640)
        '15.0 MB/s'
    """
    if bytes_per_second < 0:
        return "0 B/s"

    speed = float(bytes_per_second)
    unit_index = 0

    while speed >= 1024.0 and unit_index < len(_SPEED_UNITS) - 1:
        speed /= 1024.0
        unit_index += 1

    if unit_index == 0:
        return f"{int(speed)} {_SPEED_UNITS[unit_index]}"

    return f"{speed:.1f} {_SPEED_UNITS[unit_index]}"


def truncate_path(path: str, max_length: int = 50) -> str:
    """
    Truncate a file path to fit within a maximum length.

    Attempts to keep the filename and shorten the directory path,
    using ellipsis to indicate truncation.

    Args:
        path: File path to truncate
        max_length: Maximum length of the result

    Returns:
        str: Truncated path string

    Examples:
        >>> truncate_path("/home/user/very/long/path/to/file.txt", 30)
        '.../path/to/file.txt'
        >>> truncate_path("/short/path.txt", 30)
        '/short/path.txt'
    """
    if len(path) <= max_length:
        return path

    # Find the filename (after the last /)
    parts = path.split("/")
    filename = parts[-1]

    # If filename alone is longer than max_length
    if len(filename) >= max_length:
        return "..." + filename[-(max_length - 3) :]

    # Calculate available space for directory path
    available = max_length - len(filename) - 4  # -4 for ".../"

    if available > 0:
        directory = "/".join(parts[:-1])
        truncated_dir = directory[-available:]
        return f".../{truncated_dir}/{filename}"
    else:
        # Not enough space even with truncation
        return "..." + filename[-(max_length - 3) :]


def format_slurm_time(minutes: int) -> str:
    """
    Format minutes into SLURM time format (HH:MM:SS).

    Args:
        minutes: Time limit in minutes

    Returns:
        str: Time formatted as HH:MM:SS

    Examples:
        >>> format_slurm_time(0)
        '00:00:00'
        >>> format_slurm_time(65)
        '01:05:00'
        >>> format_slurm_time(1440)
        '24:00:00'
    """
    if minutes < 0:
        minutes = 0

    total_seconds = minutes * 60
    hours = total_seconds // 3600
    remaining = total_seconds % 3600
    mins = remaining // 60
    secs = remaining % 60

    return f"{hours:02d}:{mins:02d}:{secs:02d}"


def format_percentage(value: float, total: float, decimals: int = 1) -> str:
    """
    Format a value as a percentage of a total.

    Args:
        value: Current value
        total: Total value
        decimals: Number of decimal places

    Returns:
        str: Formatted percentage string (e.g., "50.0%")

    Examples:
        >>> format_percentage(50, 100)
        '50.0%'
        >>> format_percentage(1, 3, decimals=2)
        '33.33%'
    """
    if total == 0:
        return "0.0%"

    percentage = (value / total) * 100
    return f"{percentage:.{decimals}f}%"


def format_memory(megabytes: int) -> str:
    """
    Format memory size into a human-readable string.

    Args:
        megabytes: Memory size in megabytes

    Returns:
        str: Formatted memory string (e.g., "2.0 GB")

    Examples:
        >>> format_memory(1024)
        '1.0 GB'
        >>> format_memory(512)
        '512.0 MB'
    """
    if megabytes < 0:
        return "0 MB"

    if megabytes < 1024:
        return f"{megabytes:.1f} MB"

    gigabytes = megabytes / 1024.0

    if gigabytes < 1024:
        return f"{gigabytes:.1f} GB"

    terabytes = gigabytes / 1024.0
    return f"{terabytes:.1f} TB"


def format_cpu_cores(cores: int) -> str:
    """
    Format CPU core count into a human-readable string.

    Args:
        cores: Number of CPU cores

    Returns:
        str: Formatted core count (e.g., "4 cores", "1 core")

    Examples:
        >>> format_cpu_cores(1)
        '1 core'
        >>> format_cpu_cores(4)
        '4 cores'
    """
    if cores == 1:
        return "1 core"
    return f"{cores} cores"


def format_job_time_remaining(seconds: int) -> str:
    """
    Format remaining job time in a user-friendly format.

    Args:
        seconds: Remaining time in seconds

    Returns:
        str: Formatted time remaining string

    Examples:
        >>> format_job_time_remaining(3661)
        '~1 hour'
        >>> format_job_time_remaining(300)
        '~5 minutes'
    """
    if seconds <= 0:
        return "Expired"

    if seconds < 60:
        return "< 1 minute"

    minutes = seconds // 60

    if minutes < 60:
        return f"~{minutes} minute{'s' if minutes != 1 else ''}"

    hours = minutes // 60
    if hours < 24:
        return f"~{hours} hour{'s' if hours != 1 else ''}"

    days = hours // 24
    return f"~{days} day{'s' if days != 1 else ''}"
