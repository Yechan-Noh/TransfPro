"""
TransfPro Input Validation Utilities

This module provides validation functions for various input types including
hostnames, ports, paths, job names, and SLURM parameters.
"""

import re
import ipaddress
from pathlib import Path
from typing import Tuple

# Pre-compiled regex patterns for performance optimization
_RE_IPV4 = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")
_RE_HOSTNAME = re.compile(r"^(?!-)[a-zA-Z0-9-]{1,63}(?<!-)(\.(?!-)[a-zA-Z0-9-]{1,63}(?<!-))*$")
_RE_JOB_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_-]*$")
_RE_MEMORY = re.compile(r"^(\d+)([KMGT]?)B?$")
_RE_PARTITION = re.compile(r"^[a-zA-Z0-9_-]+$")
_RE_EMAIL = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_RE_URL = re.compile(r"^https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/.*)?$")


def validate_hostname(host: str) -> Tuple[bool, str]:
    """
    Validate a hostname or IP address.

    Supports:
    - IPv4 addresses (e.g., 192.168.1.1)
    - IPv6 addresses (e.g., ::1)
    - Hostnames (e.g., cluster.example.com)
    - Localhost variants (localhost, 127.0.0.1)

    Args:
        host: Hostname or IP address to validate

    Returns:
        Tuple[bool, str]: (is_valid, error_message)

    Examples:
        >>> validate_hostname("cluster.example.com")
        (True, '')
        >>> validate_hostname("192.168.1.1")
        (True, '')
        >>> validate_hostname("invalid host name!")
        (False, 'Invalid hostname format')
    """
    if not host or not isinstance(host, str):
        return False, "Hostname cannot be empty"

    host = host.strip()

    if len(host) > 253:
        return False, "Hostname too long (max 253 characters)"

    # IPv4 pattern
    if _RE_IPV4.match(host):
        parts = host.split(".")
        for part in parts:
            try:
                if int(part) > 255:
                    return False, "Invalid IPv4 address"
            except ValueError:
                return False, "Invalid IPv4 address"
        return True, ""

    # IPv6 pattern (simplified)
    if ":" in host:
        try:
            ipaddress.IPv6Address(host)
            return True, ""
        except ValueError:
            return False, "Invalid IPv6 address"

    # Hostname pattern (RFC 1123)
    if _RE_HOSTNAME.match(host):
        return True, ""

    return False, "Invalid hostname format"


def validate_port(port: int, allow_system_ports: bool = False) -> Tuple[bool, str]:
    """
    Validate a network port number.

    Args:
        port: Port number to validate
        allow_system_ports: If True, allows ports 1-1023 (requires elevated privileges)

    Returns:
        Tuple[bool, str]: (is_valid, error_message)

    Examples:
        >>> validate_port(22)
        (True, '')
        >>> validate_port(65535)
        (True, '')
        >>> validate_port(0)
        (False, 'Port must be between 1 and 65535')
    """
    if not isinstance(port, int):
        try:
            port = int(port)
        except (ValueError, TypeError):
            return False, "Port must be an integer"

    min_port = 1 if allow_system_ports else 1024
    max_port = 65535

    if port < min_port or port > max_port:
        return False, f"Port must be between {min_port} and {max_port}"

    return True, ""


def validate_path(path: str, must_exist: bool = False) -> Tuple[bool, str]:
    """
    Validate a file or directory path.

    Args:
        path: Path to validate
        must_exist: If True, path must exist on the filesystem

    Returns:
        Tuple[bool, str]: (is_valid, error_message)

    Examples:
        >>> validate_path("/home/user")
        (True, '')
        >>> validate_path("")
        (False, 'Path cannot be empty')
        >>> validate_path("/nonexistent/path", must_exist=True)
        (False, 'Path does not exist')
    """
    if not path or not isinstance(path, str):
        return False, "Path cannot be empty"

    path = path.strip()

    # Check for invalid characters (platform specific)
    if path.startswith("\x00"):
        return False, "Path contains null characters"

    try:
        path_obj = Path(path)

        if must_exist and not path_obj.exists():
            return False, "Path does not exist"

        return True, ""

    except (ValueError, TypeError, OSError) as e:
        return False, f"Invalid path: {str(e)}"


def validate_job_name(name: str) -> Tuple[bool, str]:
    """
    Validate a SLURM job name.

    SLURM job names:
    - Must be 1-255 characters
    - Can contain alphanumeric characters, hyphens, and underscores
    - Cannot start with a digit
    - Cannot contain spaces or special characters

    Args:
        name: Job name to validate

    Returns:
        Tuple[bool, str]: (is_valid, error_message)

    Examples:
        >>> validate_job_name("my_job")
        (True, '')
        >>> validate_job_name("job-123")
        (True, '')
        >>> validate_job_name("123job")
        (False, 'Job name cannot start with a digit')
    """
    if not name or not isinstance(name, str):
        return False, "Job name cannot be empty"

    name = name.strip()

    if len(name) > 255:
        return False, "Job name too long (max 255 characters)"

    if name[0].isdigit():
        return False, "Job name cannot start with a digit"

    # Pattern: alphanumeric, underscore, hyphen, max 255 chars
    if not _RE_JOB_NAME.match(name):
        return False, "Job name can only contain letters, numbers, hyphens, and underscores"

    return True, ""


def validate_time_limit(minutes: int, max_time: int = 10080) -> Tuple[bool, str]:
    """
    Validate a SLURM job time limit.

    Args:
        minutes: Time limit in minutes
        max_time: Maximum allowed time in minutes (default: 7 days = 10080 minutes)

    Returns:
        Tuple[bool, str]: (is_valid, error_message)

    Examples:
        >>> validate_time_limit(60)
        (True, '')
        >>> validate_time_limit(0)
        (False, 'Time limit must be at least 1 minute')
        >>> validate_time_limit(999999)
        (False, 'Time limit exceeds maximum allowed')
    """
    if not isinstance(minutes, (int, float)):
        try:
            minutes = int(minutes)
        except (ValueError, TypeError):
            return False, "Time limit must be a number"

    if minutes < 1:
        return False, "Time limit must be at least 1 minute"

    if minutes > max_time:
        return False, f"Time limit exceeds maximum allowed ({max_time} minutes)"

    return True, ""


def validate_cpu_count(cpus: int, max_cpus: int = 512) -> Tuple[bool, str]:
    """
    Validate CPU count for job submission.

    Args:
        cpus: Number of CPUs to allocate
        max_cpus: Maximum allowed CPUs (default: 512)

    Returns:
        Tuple[bool, str]: (is_valid, error_message)

    Examples:
        >>> validate_cpu_count(4)
        (True, '')
        >>> validate_cpu_count(0)
        (False, 'CPU count must be at least 1')
        >>> validate_cpu_count(1000)
        (False, 'CPU count exceeds maximum allowed')
    """
    if not isinstance(cpus, (int, float)):
        try:
            cpus = int(cpus)
        except (ValueError, TypeError):
            return False, "CPU count must be a number"

    if cpus < 1:
        return False, "CPU count must be at least 1"

    if cpus > max_cpus:
        return False, f"CPU count exceeds maximum allowed ({max_cpus})"

    return True, ""


def validate_memory(memory: str) -> Tuple[bool, str]:
    """
    Validate SLURM memory specification.

    Supports formats: 1000, 1K, 1M, 1G, 1T

    Args:
        memory: Memory specification string

    Returns:
        Tuple[bool, str]: (is_valid, error_message)

    Examples:
        >>> validate_memory("4G")
        (True, '')
        >>> validate_memory("2048M")
        (True, '')
        >>> validate_memory("invalid")
        (False, 'Invalid memory format')
    """
    if not memory or not isinstance(memory, str):
        return False, "Memory specification cannot be empty"

    memory = memory.strip().upper()

    # Pattern: number followed by optional unit (K, M, G, T)
    match = _RE_MEMORY.match(memory)

    if not match:
        return False, "Invalid memory format (use: 1000, 1K, 1M, 1G, 1T)"

    try:
        value = int(match.group(1))
        if value < 1:
            return False, "Memory value must be at least 1"
        return True, ""
    except ValueError:
        return False, "Invalid memory value"


def validate_partition_name(partition: str) -> Tuple[bool, str]:
    """
    Validate a SLURM partition name.

    Args:
        partition: Partition name to validate

    Returns:
        Tuple[bool, str]: (is_valid, error_message)

    Examples:
        >>> validate_partition_name("compute")
        (True, '')
        >>> validate_partition_name("gpu-partition")
        (True, '')
    """
    if not partition or not isinstance(partition, str):
        return False, "Partition name cannot be empty"

    partition = partition.strip()

    if len(partition) > 32:
        return False, "Partition name too long (max 32 characters)"

    if not _RE_PARTITION.match(partition):
        return False, "Partition name can only contain letters, numbers, hyphens, and underscores"

    return True, ""


def validate_email(email: str) -> Tuple[bool, str]:
    """
    Validate an email address.

    Args:
        email: Email address to validate

    Returns:
        Tuple[bool, str]: (is_valid, error_message)

    Examples:
        >>> validate_email("user@example.com")
        (True, '')
        >>> validate_email("invalid.email")
        (False, 'Invalid email format')
    """
    if not email or not isinstance(email, str):
        return False, "Email cannot be empty"

    # Simplified email pattern
    if _RE_EMAIL.match(email.strip()):
        return True, ""

    return False, "Invalid email format"


def validate_url(url: str) -> Tuple[bool, str]:
    """
    Validate a URL.

    Args:
        url: URL to validate

    Returns:
        Tuple[bool, str]: (is_valid, error_message)

    Examples:
        >>> validate_url("http://example.com")
        (True, '')
        >>> validate_url("not a url")
        (False, 'Invalid URL format')
    """
    if not url or not isinstance(url, str):
        return False, "URL cannot be empty"

    if _RE_URL.match(url.strip()):
        return True, ""

    return False, "Invalid URL format"
