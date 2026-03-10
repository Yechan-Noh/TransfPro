"""
Connection profile models for TransfPro.

This module defines data models for managing SSH connection profiles
to HPC clusters, including authentication methods and connection settings.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Dict, Any
import uuid


@dataclass
class ConnectionProfile:
    """
    Represents an SSH connection profile for connecting to HPC clusters.

    Attributes:
        id: Unique identifier (UUID) for the connection profile.
        name: Display name for the connection profile.
        host: Hostname or IP address of the remote host.
        port: SSH port number (default: 22).
        username: Username for authentication (default: empty string).
        auth_method: Authentication method - "password" or "key" (default: "password").
        key_path: Path to SSH private key file (optional).
        has_2fa: Whether two-factor authentication is required (default: False).
        two_fa_response: Response to send for 2FA approval (default: "1").
        two_fa_timeout: Seconds to wait for 2FA approval (default: 60).
        remember_password: Whether to remember password locally (default: False).
        timeout: Connection timeout in seconds (default: 10).
        auto_reconnect: Whether to automatically reconnect on disconnection (default: True).
        keepalive_interval: SSH keepalive interval in seconds (default: 30).
        created_at: Timestamp when the profile was created.
        last_connected: Timestamp of last successful connection.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    host: str = ""
    port: int = 22
    username: str = ""
    auth_method: str = "password"
    key_path: Optional[str] = None
    has_2fa: bool = False
    two_fa_response: str = "1"
    two_fa_timeout: int = 60
    remember_password: bool = False
    timeout: int = 10
    auto_reconnect: bool = True
    keepalive_interval: int = 30
    created_at: Optional[datetime] = None
    last_connected: Optional[datetime] = None

    def __post_init__(self) -> None:
        """Initialize default timestamps if not provided."""
        if self.created_at is None:
            self.created_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the ConnectionProfile to a dictionary representation.

        Returns:
            Dictionary containing all profile attributes with datetime objects
            converted to ISO format strings.
        """
        data = asdict(self)
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        if self.last_connected:
            data['last_connected'] = self.last_connected.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConnectionProfile':
        """
        Create a ConnectionProfile instance from a dictionary.

        Args:
            data: Dictionary containing profile attributes. Datetime strings
                  in ISO format are automatically converted to datetime objects.

        Returns:
            A new ConnectionProfile instance.
        """
        data_copy = data.copy()

        # Convert ISO format strings to datetime objects
        if isinstance(data_copy.get('created_at'), str):
            data_copy['created_at'] = datetime.fromisoformat(data_copy['created_at'])
        if isinstance(data_copy.get('last_connected'), str):
            data_copy['last_connected'] = datetime.fromisoformat(data_copy['last_connected'])

        return cls(**data_copy)

    def copy(self) -> 'ConnectionProfile':
        """
        Create a shallow copy of the ConnectionProfile.

        The copy will have a new UUID assigned while preserving all other attributes.

        Returns:
            A new ConnectionProfile instance with copied attributes.
        """
        return ConnectionProfile(
            id=str(uuid.uuid4()),
            name=self.name,
            host=self.host,
            port=self.port,
            username=self.username,
            auth_method=self.auth_method,
            key_path=self.key_path,
            has_2fa=self.has_2fa,
            two_fa_response=self.two_fa_response,
            two_fa_timeout=self.two_fa_timeout,
            remember_password=self.remember_password,
            timeout=self.timeout,
            auto_reconnect=self.auto_reconnect,
            keepalive_interval=self.keepalive_interval,
            created_at=self.created_at,
            last_connected=self.last_connected,
        )
