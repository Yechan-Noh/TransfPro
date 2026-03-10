"""Desktop notification system for TransfPro."""

import logging
import subprocess
import platform
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class NotificationManager:
    """Desktop notification system with optional Qt integration."""

    def __init__(self, tray_icon: Optional[object] = None, database: Optional[object] = None):
        """
        Initialize notification manager.

        Args:
            tray_icon: Optional QSystemTrayIcon for showing notifications
            database: Optional Database instance for logging notifications
        """
        self.tray_icon = tray_icon
        self.db = database
        self.system = platform.system()
        logger.debug(f"Notification manager initialized for {self.system}")

    def notify_job_completed(self, job):
        """
        Send job completion notification.

        Args:
            job: JobInfo object
        """
        title = f"Job Completed: {job.name}"
        message = f"Job ID: {job.job_id}\nUser: {job.user}\nQueue: {job.queue}"

        self.notify(title, message, icon_type="success")

        # Log to database
        if self.db:
            self.db.save_notification(
                "job_completed",
                f"{job.name} (ID: {job.job_id}) completed",
                job.job_id
            )

    def notify_job_failed(self, job):
        """
        Send job failure notification.

        Args:
            job: JobInfo object
        """
        title = f"Job Failed: {job.name}"
        message = (
            f"Job ID: {job.job_id}\n"
            f"User: {job.user}\n"
            f"Exit Code: {job.exit_code}"
        )

        self.notify(title, message, icon_type="error")

        # Log to database
        if self.db:
            self.db.save_notification(
                "job_failed",
                f"{job.name} (ID: {job.job_id}) failed with exit code {job.exit_code}",
                job.job_id
            )

    def notify_transfer_completed(self, transfer):
        """
        Send file transfer completion notification.

        Args:
            transfer: TransferTask object with attributes:
                     - transfer_type: 'upload' or 'download'
                     - local_path: Local file path
                     - remote_path: Remote file path
                     - file_size: Total bytes transferred
        """
        transfer_type = getattr(transfer, 'transfer_type', 'transfer').title()
        local_path = getattr(transfer, 'local_path', '')
        remote_path = getattr(transfer, 'remote_path', '')

        # Extract just the filename for display
        local_file = local_path.split('/')[-1] if local_path else 'file'
        remote_file = remote_path.split('/')[-1] if remote_path else 'file'

        title = f"{transfer_type} Complete"
        message = f"{local_file} <-> {remote_file}\nSuccessfully transferred"

        self.notify(title, message, icon_type="success")

        # Log to database
        if self.db:
            self.db.save_notification(
                "transfer_completed",
                f"{transfer_type}: {local_path} to {remote_path}"
            )

    def notify_connection_lost(self):
        """Send connection lost notification."""
        title = "Connection Lost"
        message = "SSH connection to remote host was lost"

        self.notify(title, message, icon_type="warning")

        # Log to database
        if self.db:
            self.db.save_notification(
                "connection_lost",
                "SSH connection was lost"
            )

    def notify_connection_restored(self):
        """Send connection restored notification."""
        title = "Connection Restored"
        message = "SSH connection to remote host has been restored"

        self.notify(title, message, icon_type="success")

        # Log to database
        if self.db:
            self.db.save_notification(
                "connection_restored",
                "SSH connection was restored"
            )

    def notify(self, title: str, message: str, icon_type: str = "info"):
        """
        Send desktop notification.

        Uses Qt tray icon if available, otherwise uses system notifications.

        Args:
            title: Notification title
            message: Notification message
            icon_type: Icon type ('info', 'success', 'warning', 'error')
        """
        logger.info(f"Notification: {title}")
        logger.debug(f"Message: {message}")

        # Try to show in Qt tray icon first
        if self.tray_icon:
            self._notify_qt_tray(title, message, icon_type)
        else:
            # Fall back to system notification
            self._notify_system(title, message, icon_type)

    def _notify_qt_tray(self, title: str, message: str, icon_type: str):
        """
        Show notification via Qt system tray.

        Args:
            title: Notification title
            message: Notification message
            icon_type: Icon type
        """
        try:
            # Map icon type to Qt MessageIcon enum values
            icon_map = {
                "info": 1,      # QSystemTrayIcon.Information
                "success": 1,   # Also Information
                "warning": 2,   # QSystemTrayIcon.Warning
                "error": 3,     # QSystemTrayIcon.Critical
            }

            icon_value = icon_map.get(icon_type, 1)

            # Show notification (2000ms duration)
            self.tray_icon.showMessage(title, message, icon_value, 2000)
            logger.debug(f"Showed Qt tray notification: {title}")

        except Exception as e:
            logger.warning(f"Failed to show Qt tray notification: {e}")
            # Fall back to system notification
            self._notify_system(title, message, icon_type)

    def _notify_system(self, title: str, message: str, icon_type: str):
        """
        Show notification using system notification system.

        Supports Linux (notify-send), macOS (osascript), and Windows (PowerShell).

        Args:
            title: Notification title
            message: Notification message
            icon_type: Icon type
        """
        try:
            if self.system == "Linux":
                self._notify_linux(title, message, icon_type)
            elif self.system == "Darwin":  # macOS
                self._notify_macos(title, message)
            elif self.system == "Windows":
                self._notify_windows(title, message, icon_type)
            else:
                logger.warning(f"Notification system not supported on {self.system}")

        except Exception as e:
            logger.error(f"Failed to send system notification: {e}")

    def _notify_linux(self, title: str, message: str, icon_type: str):
        """
        Send Linux notification using notify-send.

        Args:
            title: Notification title
            message: Notification message
            icon_type: Icon type (info, success, warning, error)
        """
        try:
            icon_map = {
                "info": "dialog-information",
                "success": "dialog-positive",
                "warning": "dialog-warning",
                "error": "dialog-error",
            }

            icon = icon_map.get(icon_type, "dialog-information")
            urgency = "critical" if icon_type == "error" else "normal"

            # Limit message length
            display_msg = message[:200]

            subprocess.run(
                [
                    "notify-send",
                    "-i", icon,
                    "-u", urgency,
                    title,
                    display_msg
                ],
                check=False,
                timeout=5
            )
            logger.debug("Linux notification sent via notify-send")

        except Exception as e:
            logger.debug(f"notify-send not available: {e}")

    def _notify_macos(self, title: str, message: str):
        """
        Send macOS notification via Qt tray icon.

        We intentionally avoid osascript/AppleScript because every call
        triggers a macOS "would like to access data from other apps"
        permission prompt, which is extremely disruptive.

        Args:
            title: Notification title
            message: Notification message
        """
        # If we have a tray icon, use it (already handled by caller).
        # Otherwise just log — no osascript.
        logger.debug(f"macOS notification (logged only): {title} — {message}")

    def _notify_windows(self, title: str, message: str, icon_type: str):
        """
        Send Windows notification using PowerShell Toast.

        Args:
            title: Notification title
            message: Notification message
            icon_type: Icon type
        """
        try:
            # Escape quotes in title and message
            title = title.replace('"', '\\"')
            message = message.replace('"', '\\"')

            # PowerShell script for notification
            ps_script = (
                '[Windows.UI.Notifications.ToastNotificationManager, '
                'Windows.UI.Notifications, ContentType = WindowsRuntime] > $null\n'
                '[Windows.UI.Notifications.ToastNotification, '
                'Windows.UI.Notifications, ContentType = WindowsRuntime] > $null\n'
                '[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, '
                'ContentType = WindowsRuntime] > $null\n'
                '\n'
                '$APP_ID = "TransfPro"\n'
                '$template = @"\n'
                '<toast>\n'
                '    <visual>\n'
                f'        <binding template="ToastText02">\n'
                f'            <text id="1">{title}</text>\n'
                f'            <text id="2">{message}</text>\n'
                f'        </binding>\n'
                f'    </visual>\n'
                f'</toast>\n'
                f'"@\n'
                '\n'
                '$xml = New-Object Windows.Data.Xml.Dom.XmlDocument\n'
                '$xml.LoadXml($template)\n'
                '$toast = New-Object Windows.UI.Notifications.ToastNotification $xml\n'
                '[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($APP_ID).Show($toast)'
            )

            subprocess.run(
                ["powershell", "-Command", ps_script],
                check=False,
                timeout=5
            )
            logger.debug("Windows notification sent via PowerShell")

        except Exception as e:
            logger.debug(f"PowerShell notification failed: {e}")

    def notify_simple(self, title: str, message: str):
        """
        Send simple notification without logging to database.

        Useful for transient notifications.

        Args:
            title: Notification title
            message: Notification message
        """
        self.notify(title, message, icon_type="info")

    def notify_error(self, title: str, message: str):
        """
        Send error notification.

        Args:
            title: Notification title
            message: Error message
        """
        self.notify(title, message, icon_type="error")

        if self.db:
            self.db.save_notification("error", f"{title}: {message}")

    def notify_warning(self, title: str, message: str):
        """
        Send warning notification.

        Args:
            title: Notification title
            message: Warning message
        """
        self.notify(title, message, icon_type="warning")

        if self.db:
            self.db.save_notification("warning", f"{title}: {message}")
