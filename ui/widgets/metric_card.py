"""
Metric card widget for TransfPro dashboard.

This module provides a reusable KPI metric card widget that displays a single
metric with title, value, icon, and optional trend indicators.
"""

import logging
from typing import Optional

from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor

logger = logging.getLogger(__name__)


class MetricCard(QFrame):
    """
    Single KPI metric card with title, value, and optional trend.

    A styled card widget for displaying a single metric with:
    - Rounded border with frame style
    - Background color with accent tint
    - Icon/emoji on the left (24px)
    - Title (small, grey, 10px)
    - Value (large, bold, 24px, colored)
    - Optional subtitle/trend text (small, colored)

    Fixed height 100px, minimum width 180px.
    """

    def __init__(self, title: str, value: str = "0", color: str = "#2196F3",
                 icon_text: str = "", parent=None):
        """
        Initialize the metric card.

        Args:
            title: Card title/label (e.g., "Jobs Running")
            value: Initial value to display (e.g., "5")
            color: Accent color as hex string (e.g., "#2196F3" for blue)
            icon_text: Icon or emoji to display on the left (e.g., "▶")
            parent: Parent widget
        """
        super().__init__(parent)
        self.setObjectName("MetricCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Plain)
        self.setLineWidth(1)
        self.setFixedHeight(100)
        self.setMinimumWidth(180)

        # Store original color for styling
        self.accent_color = color
        self.title_text = title
        self.value_text = value
        self.icon_text = icon_text

        # Initialize subtitle and subtitle color
        self.subtitle_text = ""
        self.subtitle_color = "#6e738d"

        # Apply stylesheet
        self._apply_stylesheet()

        # Create layout
        self._setup_ui()

    def _apply_stylesheet(self):
        """Apply styling to the metric card."""
        # Convert hex color to RGB for background tint
        hex_color = self.accent_color.lstrip("#")
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        bg_color = f"rgb({rgb[0]}, {rgb[1]}, {rgb[2]})"

        # Create a lighter background version (30% opacity effect)
        bg_rgba = f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, 30)"

        stylesheet = f"""
            QFrame#MetricCard {{
                background-color: {bg_rgba};
                border: 1px solid {self.accent_color};
                border-radius: 6px;
                padding: 12px;
            }}
        """
        self.setStyleSheet(stylesheet)

    def _setup_ui(self):
        """Set up the metric card layout."""
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(12)

        # Left section: Icon
        if self.icon_text:
            icon_label = QLabel(self.icon_text)
            icon_label.setFont(QFont("Arial", 24, QFont.Bold))
            icon_label.setAlignment(Qt.AlignCenter)
            icon_label.setFixedWidth(40)
            icon_label.setStyleSheet("color: " + self.accent_color + ";")
            main_layout.addWidget(icon_label)

        # Right section: Title and Value (vertical layout)
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(2)

        # Title label
        self.title_label = QLabel(self.title_text)
        self.title_label.setFont(QFont("Arial", 9, QFont.Normal))
        self.title_label.setStyleSheet("color: #6e738d;")
        right_layout.addWidget(self.title_label)

        # Value label
        self.value_label = QLabel(self.value_text)
        self.value_label.setFont(QFont("Arial", 24, QFont.Bold))
        self.value_label.setStyleSheet("color: " + self.accent_color + ";")
        self.value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        right_layout.addWidget(self.value_label)

        # Subtitle label
        self.subtitle_label = QLabel("")
        self.subtitle_label.setFont(QFont("Arial", 8, QFont.Normal))
        self.subtitle_label.setStyleSheet("color: " + self.subtitle_color + ";")
        self.subtitle_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        right_layout.addWidget(self.subtitle_label)

        right_layout.addStretch()
        main_layout.addLayout(right_layout, 1)

        self.setLayout(main_layout)

    def set_value(self, value: str):
        """
        Update the metric value.

        Args:
            value: New value to display
        """
        self.value_text = str(value)
        self.value_label.setText(self.value_text)

    def set_subtitle(self, text: str, color: str = "#6e738d"):
        """
        Set subtitle/trend text below the value.

        Args:
            text: Subtitle text (e.g., "+2" for trend)
            color: Color for the subtitle text as hex string
        """
        self.subtitle_text = text
        self.subtitle_color = color
        self.subtitle_label.setText(text)
        self.subtitle_label.setStyleSheet("color: " + color + ";")

    def set_color(self, color: str):
        """
        Change the card accent color.

        Args:
            color: New accent color as hex string (e.g., "#FF9800" for orange)
        """
        self.accent_color = color
        self._apply_stylesheet()

        # Update icon color
        if self.icon_text:
            for child in self.findChildren(QLabel):
                if child.text() == self.icon_text:
                    child.setStyleSheet("color: " + color + ";")

        # Update value label color
        self.value_label.setStyleSheet("color: " + color + ";")

    def set_title(self, title: str):
        """
        Update the card title.

        Args:
            title: New title text
        """
        self.title_text = title
        self.title_label.setText(title)

    def set_icon(self, icon_text: str):
        """
        Update the card icon/emoji.

        Args:
            icon_text: New icon text or emoji
        """
        self.icon_text = icon_text
        # Regenerate UI to update icon
        self.layout().deleteLater()
        self._setup_ui()
