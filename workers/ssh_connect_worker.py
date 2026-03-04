"""
Worker thread for SSH connection operations.

This module provides a background worker for establishing SSH connections
with support for 2FA and connection state tracking.
"""

import logging
from typing import Optional
from PyQt5.QtCore import pyqtSignal

from transfpro.workers.base_worker import BaseWorker
from transfpro.models.connection import ConnectionProfile
from transfpro.core.ssh_manager import SSHManager

logger = logging.getLogger(__name__)


class SSHConnectWorker(BaseWorker):
    """Background worker for SSH connection operations.

    Handles establishing SSH connections with automatic 2FA support.
    Runs in a background thread to avoid blocking the UI.

    Signals:
        connected: Emitted when connection is successful
        connection_failed: Emitted when connection fails (str error_message)
        waiting_for_2fa: Emitted when waiting for 2FA response
        status_message: Emitted for status updates
        error: Emitted for errors
    """

    connected = pyqtSignal()
    connection_failed = pyqtSignal(str)  # error message
    waiting_for_2fa = pyqtSignal()
    two_fa_response_received = pyqtSignal(str)  # response text

    def __init__(
        self,
        ssh_manager: SSHManager,
        profile: ConnectionProfile,
        password: Optional[str] = None
    ):
        """Initialize the SSH connection worker.

        Args:
            ssh_manager: SSHManager instance
            profile: ConnectionProfile to connect with
            password: SSH password (if using password auth)
        """
        super().__init__()
        self.ssh_manager = ssh_manager
        self.profile = profile
        self.password = password

    def do_work(self):
        """Perform the SSH connection work in background thread."""
        try:
            self.status_message.emit(
                f"Connecting to {self.profile.host}:{self.profile.port}..."
            )
            self.logger.info(
                f"Starting SSH connection to {self.profile.host}:{self.profile.port} "
                f"as {self.profile.username}"
            )

            # Emit 2FA waiting signal if 2FA is enabled
            if self.profile.has_2fa:
                self.logger.info("2FA enabled, waiting for device approval...")
                self.waiting_for_2fa.emit()
                self.status_message.emit(
                    f"Waiting for 2FA approval on your phone "
                    f"(timeout: {self.profile.two_fa_timeout}s)..."
                )

            # Check for cancellation
            if self.is_cancelled:
                self.logger.info("Connection cancelled by user")
                self.connection_failed.emit("Connection cancelled by user")
                return

            # Call SSH manager to connect
            success = self.ssh_manager.connect(self.profile, self.password)

            if self.is_cancelled:
                self.logger.info("Connection cancelled by user")
                self.connection_failed.emit("Connection cancelled by user")
                return

            if success:
                self.logger.info(f"Connected to {self.profile.host}")
                self.status_message.emit(f"Connected to {self.profile.host}")
                self.connected.emit()
            else:
                error_msg = f"Failed to connect to {self.profile.host}"
                self.logger.error(error_msg)
                self.status_message.emit(error_msg)
                self.connection_failed.emit(error_msg)

        except Exception as e:
            error_msg = f"Connection error: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.status_message.emit(error_msg)
            self.connection_failed.emit(error_msg)


class SSHDisconnectWorker(BaseWorker):
    """Background worker for SSH disconnection operations.

    Handles graceful disconnection from SSH servers.
    Runs in a background thread to avoid blocking the UI.

    Signals:
        disconnected: Emitted when disconnection is successful
        disconnect_failed: Emitted when disconnection fails (str error_message)
        status_message: Emitted for status updates
        error: Emitted for errors
    """

    disconnected = pyqtSignal()
    disconnect_failed = pyqtSignal(str)  # error message

    def __init__(self, ssh_manager: SSHManager, hostname: str = ""):
        """Initialize the SSH disconnection worker.

        Args:
            ssh_manager: SSHManager instance
            hostname: Hostname for status messages
        """
        super().__init__()
        self.ssh_manager = ssh_manager
        self.hostname = hostname

    def do_work(self):
        """Perform the SSH disconnection work in background thread."""
        try:
            if self.hostname:
                self.status_message.emit(f"Disconnecting from {self.hostname}...")
            else:
                self.status_message.emit("Disconnecting...")

            self.logger.info("Starting SSH disconnection")

            # Call SSH manager to disconnect
            self.ssh_manager.disconnect()

            self.logger.info("Disconnected successfully")
            self.status_message.emit("Disconnected")
            self.disconnected.emit()

        except Exception as e:
            error_msg = f"Disconnection error: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.status_message.emit(error_msg)
            self.disconnect_failed.emit(error_msg)
