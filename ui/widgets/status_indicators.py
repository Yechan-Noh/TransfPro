"""
Status indicator widgets for TransfPro UI.

This module provides reusable status indicator components including connection
status display, transfer status, and colored status lights for the UI.
"""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QProgressBar
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush


class StatusLight(QWidget):
    """
    A simple colored circle indicator widget.

    Shows a filled circle with border in various colors to indicate status.
    Common colors: "green" (connected), "red" (disconnected), "yellow" (connecting),
    "orange" (waiting), "grey" (inactive).
    """

    def __init__(self, color: str = "grey", size: int = 12, parent=None):
        """
        Initialize the status light.

        Args:
            color: Initial color name ("green", "red", "yellow", "orange", "grey")
            size: Diameter of the circle in pixels
            parent: Parent widget
        """
        super().__init__(parent)
        self.color = color
        self.size = size
        self.setFixedSize(size, size)

        # Color mappings
        self.colors = {
            "green": QColor(76, 175, 80),      # #4CAF50
            "red": QColor(244, 67, 54),        # #F44336
            "yellow": QColor(255, 193, 7),    # #FFC107
            "orange": QColor(255, 152, 0),    # #FF9800
            "grey": QColor(158, 158, 158),    # #9E9E9E
        }

    def set_color(self, color: str):
        """
        Change the indicator color.

        Args:
            color: Color name ("green", "red", "yellow", "orange", "grey")
        """
        if color in self.colors:
            self.color = color
            self.update()

    def paintEvent(self, event):
        """Paint the colored circle."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get the color
        brush_color = self.colors.get(self.color, self.colors["grey"])

        # Draw filled circle
        painter.setBrush(QBrush(brush_color))
        painter.setPen(QPen(brush_color.darker(120), 1))
        painter.drawEllipse(0, 0, self.size, self.size)


class ConnectionStatusWidget(QWidget):
    """
    Compact connection status indicator for display in status bar or panels.

    Shows a colored dot with text describing the connection state.
    States: Connected, Disconnected, Connecting, Waiting for 2FA.
    """

    def __init__(self, parent=None):
        """Initialize the connection status widget."""
        super().__init__(parent)
        self._setup_ui()
        self.set_disconnected()

    def _setup_ui(self):
        """Set up the UI layout."""
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Status light (colored circle)
        self.status_light = StatusLight(color="grey", size=10, parent=self)
        layout.addWidget(self.status_light)

        # Status text
        self.status_label = QLabel("Disconnected")
        self.status_label.setMinimumWidth(150)
        layout.addWidget(self.status_label)

        # Spacer
        layout.addStretch()

        self.setLayout(layout)

    def set_connected(self, hostname: str):
        """
        Set status to connected.

        Args:
            hostname: The hostname we're connected to
        """
        self.status_light.set_color("green")
        self.status_label.setText(f"Connected to {hostname}")
        self.status_label.setToolTip(f"SSH connection active: {hostname}")

    def set_disconnected(self):
        """Set status to disconnected."""
        self.status_light.set_color("red")
        self.status_label.setText("Disconnected")
        self.status_label.setToolTip("Not connected to any cluster")

    def set_connecting(self):
        """Set status to connecting."""
        self.status_light.set_color("yellow")
        self.status_label.setText("Connecting...")
        self.status_label.setToolTip("SSH connection in progress")

    def set_2fa_waiting(self):
        """Set status to waiting for 2FA response."""
        self.status_light.set_color("orange")
        self.status_label.setText("Waiting for 2FA...")
        self.status_label.setToolTip("Awaiting two-factor authentication confirmation")

    def set_error(self, error_message: str):
        """
        Set status to error with message.

        Args:
            error_message: Description of the error
        """
        self.status_light.set_color("red")
        self.status_label.setText(f"Error: {error_message}")
        self.status_label.setToolTip(error_message)


class TransferStatusWidget(QWidget):
    """
    Shows active transfer count and overall progress.

    Displays the number of active transfers and a mini progress bar
    showing the overall transfer completion percentage.
    """

    def __init__(self, parent=None):
        """Initialize the transfer status widget."""
        super().__init__(parent)
        self._setup_ui()
        self.update_status(0, 0.0)

    def _setup_ui(self):
        """Set up the UI layout."""
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Transfer icon/label
        self.transfer_label = QLabel("0 transfers active")
        self.transfer_label.setMinimumWidth(140)
        layout.addWidget(self.transfer_label)

        # Mini progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(150)
        self.progress_bar.setMaximumHeight(16)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        layout.addStretch()

        self.setLayout(layout)

    def update_status(self, active_count: int, overall_percent: float):
        """
        Update the transfer status display.

        Args:
            active_count: Number of active transfers
            overall_percent: Overall progress percentage (0-100)
        """
        # Update label
        if active_count == 0:
            self.transfer_label.setText("No active transfers")
            self.transfer_label.setToolTip("Ready for file transfers")
        elif active_count == 1:
            self.transfer_label.setText("1 transfer active")
            self.transfer_label.setToolTip("1 file transfer in progress")
        else:
            self.transfer_label.setText(f"{active_count} transfers active")
            self.transfer_label.setToolTip(f"{active_count} file transfers in progress")

        # Update progress bar
        self.progress_bar.setValue(int(overall_percent))
        if active_count == 0:
            self.progress_bar.setVisible(False)
        else:
            self.progress_bar.setVisible(True)


class IndicatorLabel(QWidget):
    """
    Combines a status light with a text label for status displays.

    Flexible widget that can show any status with an indicator light
    and accompanying text.
    """

    def __init__(self, initial_text: str = "", color: str = "grey", parent=None):
        """
        Initialize the indicator label.

        Args:
            initial_text: Initial text to display
            color: Initial indicator color
            parent: Parent widget
        """
        super().__init__(parent)
        self._setup_ui(color, initial_text)

    def _setup_ui(self, color: str, text: str):
        """Set up the UI layout."""
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.light = StatusLight(color=color, size=8, parent=self)
        layout.addWidget(self.light)

        self.label = QLabel(text)
        layout.addWidget(self.label)

        self.setLayout(layout)

    def set_color(self, color: str):
        """
        Set the indicator light color.

        Args:
            color: Color name
        """
        self.light.set_color(color)

    def set_text(self, text: str):
        """
        Set the label text.

        Args:
            text: Text to display
        """
        self.label.setText(text)

    def set_status(self, color: str, text: str):
        """
        Set both color and text.

        Args:
            color: Indicator color
            text: Label text
        """
        self.set_color(color)
        self.set_text(text)
