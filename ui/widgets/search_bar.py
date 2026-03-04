"""
Reusable search/filter bar widget.

This module provides a SearchBar widget with text input, clear button, and optional
filter dropdown. It includes debouncing for search text changes.
"""

import logging
from typing import Optional, List
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLineEdit, QComboBox, QPushButton
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QIcon

logger = logging.getLogger(__name__)


class SearchBar(QWidget):
    """Search bar with text input and optional filter dropdown."""

    search_changed = pyqtSignal(str)  # search text
    filter_changed = pyqtSignal(str)  # filter value

    def __init__(self, placeholder: str = "Search...",
                 filters: Optional[List[str]] = None, parent=None):
        """
        Initialize the search bar.

        Args:
            placeholder: Placeholder text for search input
            filters: Optional list of filter options
            parent: Parent widget
        """
        super().__init__(parent)
        self.filters = filters or []
        self._setup_ui(placeholder)
        self._setup_debounce()

    def _setup_ui(self, placeholder: str):
        """Set up the UI layout."""
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(placeholder)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        layout.addWidget(self.search_input)

        # Clear button
        self.clear_button = QPushButton()
        self.clear_button.setText("✕")
        self.clear_button.setMaximumWidth(32)
        self.clear_button.setToolTip("Clear search")
        self.clear_button.clicked.connect(self._on_clear)
        layout.addWidget(self.clear_button)

        # Filter dropdown (optional)
        if self.filters:
            self.filter_combo = QComboBox()
            self.filter_combo.addItems(self.filters)
            self.filter_combo.currentTextChanged.connect(self.filter_changed.emit)
            layout.addWidget(self.filter_combo)

        self.setLayout(layout)

    def _setup_debounce(self):
        """Set up debounce timer for search input."""
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(
            lambda: self.search_changed.emit(self.get_search_text())
        )

    def _on_search_text_changed(self):
        """Handle search text changes with debouncing."""
        self.debounce_timer.stop()
        self.debounce_timer.start(300)  # 300ms delay

    def _on_clear(self):
        """Clear the search input."""
        self.search_input.clear()

    def get_search_text(self) -> str:
        """Get the current search text."""
        return self.search_input.text().strip()

    def get_filter_value(self) -> Optional[str]:
        """Get the current filter value."""
        if hasattr(self, 'filter_combo'):
            return self.filter_combo.currentText()
        return None

    def set_search_text(self, text: str):
        """Set the search text programmatically."""
        self.search_input.blockSignals(True)
        self.search_input.setText(text)
        self.search_input.blockSignals(False)

    def set_filter_value(self, value: str):
        """Set the filter value programmatically."""
        if hasattr(self, 'filter_combo'):
            index = self.filter_combo.findText(value)
            if index >= 0:
                self.filter_combo.setCurrentIndex(index)
