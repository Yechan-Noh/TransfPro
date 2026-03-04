"""
Transfer confirmation dialog for handling file conflicts.

This module provides a dialog for confirming file transfers when conflicts
occur (e.g., destination file already exists), with options to overwrite,
skip, or cancel the transfer.
"""

import logging
from typing import List, Dict, Tuple
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QScrollArea,
    QWidget, QFrame, QMessageBox, QCheckBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QIcon, QColor

logger = logging.getLogger(__name__)


class ConflictItemWidget(QWidget):
    """Widget displaying a single file conflict."""

    def __init__(self, conflict: Dict, parent=None):
        """
        Initialize conflict item widget.

        Args:
            conflict: Dictionary with keys:
                - source_path: str
                - dest_path: str
                - source_size: int
                - dest_size: int
                - source_date: datetime
                - dest_date: datetime
            parent: Parent widget
        """
        super().__init__(parent)
        self.conflict = conflict
        self.resolution = None  # "overwrite", "skip", or None
        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI components."""
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        # File name
        filename = self.conflict.get('filename', 'Unknown')
        filename_label = QLabel(filename)
        filename_font = QFont()
        filename_font.setBold(True)
        filename_font.setPointSize(10)
        filename_label.setFont(filename_font)
        layout.addWidget(filename_label)

        # Source file info
        source_layout = QHBoxLayout()
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(16)

        source_section = QVBoxLayout()
        source_section.setContentsMargins(0, 0, 0, 0)
        source_section.setSpacing(4)

        source_label = QLabel("Source File")
        source_font = QFont()
        source_font.setBold(True)
        source_font.setPointSize(9)
        source_label.setFont(source_font)
        source_section.addWidget(source_label)

        source_path = self.conflict.get('source_path', 'Unknown')
        source_path_label = QLabel(source_path)
        source_path_label.setStyleSheet("color: gray; font-size: 8pt;")
        source_path_label.setToolTip(source_path)
        source_path_label.setWordWrap(True)
        source_section.addWidget(source_path_label)

        source_size = self._format_size(self.conflict.get('source_size', 0))
        source_date = self.conflict.get('source_date', datetime.now())
        source_date_str = (source_date.strftime("%Y-%m-%d %H:%M:%S")
                          if source_date else "Unknown")
        source_info = f"Size: {source_size} | Modified: {source_date_str}"
        source_info_label = QLabel(source_info)
        source_info_label.setStyleSheet("font-size: 8pt;")
        source_section.addWidget(source_info_label)

        source_layout.addLayout(source_section, 1)

        # Destination file info
        dest_section = QVBoxLayout()
        dest_section.setContentsMargins(0, 0, 0, 0)
        dest_section.setSpacing(4)

        dest_label = QLabel("Existing Destination")
        dest_font = QFont()
        dest_font.setBold(True)
        dest_font.setPointSize(9)
        dest_label.setFont(dest_font)
        dest_section.addWidget(dest_label)

        dest_path = self.conflict.get('dest_path', 'Unknown')
        dest_path_label = QLabel(dest_path)
        dest_path_label.setStyleSheet("color: gray; font-size: 8pt;")
        dest_path_label.setToolTip(dest_path)
        dest_path_label.setWordWrap(True)
        dest_section.addWidget(dest_path_label)

        dest_size = self._format_size(self.conflict.get('dest_size', 0))
        dest_date = self.conflict.get('dest_date', datetime.now())
        dest_date_str = (dest_date.strftime("%Y-%m-%d %H:%M:%S")
                        if dest_date else "Unknown")
        dest_info = f"Size: {dest_size} | Modified: {dest_date_str}"
        dest_info_label = QLabel(dest_info)
        dest_info_label.setStyleSheet("font-size: 8pt;")
        dest_section.addWidget(dest_info_label)

        source_layout.addLayout(dest_section, 1)

        layout.addLayout(source_layout)

        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)

        overwrite_button = QPushButton("Overwrite")
        overwrite_button.clicked.connect(lambda: self._set_resolution("overwrite"))
        overwrite_button.setMaximumWidth(100)
        button_layout.addWidget(overwrite_button)

        skip_button = QPushButton("Skip")
        skip_button.clicked.connect(lambda: self._set_resolution("skip"))
        skip_button.setMaximumWidth(100)
        button_layout.addWidget(skip_button)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _set_resolution(self, resolution: str):
        """Set the resolution for this conflict."""
        self.resolution = resolution

    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to human-readable size."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"

    def get_resolution(self) -> str:
        """Get the resolution for this conflict."""
        return self.resolution or "skip"


class TransferConfirmDialog(QDialog):
    """Dialog for confirming file transfers with overwrite options."""

    def __init__(self, conflicts: List[Dict], parent=None):
        """
        Initialize transfer confirmation dialog.

        Args:
            conflicts: List of conflict dictionaries, each containing:
                - filename: str
                - source_path: str
                - dest_path: str
                - source_size: int
                - dest_size: int
                - source_date: datetime
                - dest_date: datetime
            parent: Parent widget
        """
        super().__init__(parent)
        self.conflicts = conflicts
        self.conflict_widgets: List[ConflictItemWidget] = []
        self.resolutions: Dict[str, str] = {}  # dest_path -> resolution
        self._setup_ui()

    def _setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("Confirm File Transfers")
        self.setModal(True)
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header_label = QLabel(f"File Conflicts ({len(self.conflicts)} items)")
        header_font = QFont()
        header_font.setBold(True)
        header_font.setPointSize(11)
        header_label.setFont(header_font)
        layout.addWidget(header_label)

        description_label = QLabel(
            "The following files already exist at the destination. "
            "Choose to overwrite or skip each file."
        )
        description_label.setStyleSheet("color: gray;")
        description_label.setWordWrap(True)
        layout.addWidget(description_label)

        # Conflict items in scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; }")

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(0)

        # Add conflict widgets
        for conflict in self.conflicts:
            conflict_widget = ConflictItemWidget(conflict)
            self.conflict_widgets.append(conflict_widget)
            scroll_layout.addWidget(conflict_widget)

        scroll_layout.addStretch()
        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

        # Global options
        options_layout = QHBoxLayout()
        options_layout.setContentsMargins(0, 0, 0, 0)
        options_layout.setSpacing(16)

        # "Apply to all" checkbox
        self.apply_to_all_checkbox = QCheckBox("Apply to all conflicts")
        self.apply_to_all_checkbox.setToolTip(
            "Apply the selected action to all remaining conflicts"
        )
        options_layout.addWidget(self.apply_to_all_checkbox)

        options_layout.addStretch()

        layout.addLayout(options_layout)

        # Dialog buttons
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)

        overwrite_all_button = QPushButton("Overwrite All")
        overwrite_all_button.clicked.connect(self._on_overwrite_all)
        button_layout.addWidget(overwrite_all_button)

        skip_all_button = QPushButton("Skip All")
        skip_all_button.clicked.connect(self._on_skip_all)
        button_layout.addWidget(skip_all_button)

        button_layout.addStretch()

        cancel_button = QPushButton("Cancel Transfer")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        confirm_button = QPushButton("Apply")
        confirm_button.setDefault(True)
        confirm_button.clicked.connect(self._on_apply)
        button_layout.addWidget(confirm_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _on_overwrite_all(self):
        """Set all conflicts to overwrite."""
        for widget in self.conflict_widgets:
            widget._set_resolution("overwrite")
            # Update UI to show selection
            self._update_widget_appearance(widget, "overwrite")

    def _on_skip_all(self):
        """Set all conflicts to skip."""
        for widget in self.conflict_widgets:
            widget._set_resolution("skip")
            # Update UI to show selection
            self._update_widget_appearance(widget, "skip")

    def _update_widget_appearance(self, widget: ConflictItemWidget, resolution: str):
        """Update widget appearance to show selected resolution."""
        # This could highlight the selected action button
        # For now, just a visual update indication
        if resolution == "overwrite":
            widget.setStyleSheet("background-color: #fff3cd;")  # Light yellow
        else:
            widget.setStyleSheet("background-color: #f8f9fa;")  # Light gray

    def _on_apply(self):
        """Collect resolutions and accept dialog."""
        self.resolutions.clear()

        for i, conflict in enumerate(self.conflicts):
            if i < len(self.conflict_widgets):
                widget = self.conflict_widgets[i]
                dest_path = conflict.get('dest_path', '')
                resolution = widget.get_resolution()
                self.resolutions[dest_path] = resolution

        self.accept()

    def get_resolutions(self) -> Dict[str, str]:
        """
        Get the resolutions for all conflicts.

        Returns:
            Dictionary mapping destination path to resolution ("overwrite" or "skip")
        """
        return self.resolutions

    def get_resolution_for_path(self, dest_path: str) -> str:
        """
        Get resolution for a specific destination path.

        Args:
            dest_path: Destination file path

        Returns:
            "overwrite" or "skip"
        """
        return self.resolutions.get(dest_path, "skip")

    @staticmethod
    def check_conflicts(local_paths: List[str], remote_dir: str,
                       sftp_manager) -> List[Dict]:
        """
        Check for file conflicts before transfer.

        Args:
            local_paths: List of local file paths to transfer
            remote_dir: Remote destination directory
            sftp_manager: SFTPManager instance

        Returns:
            List of conflict dictionaries (empty if no conflicts)
        """
        conflicts = []

        try:
            import os
            from pathlib import Path

            for local_path in local_paths:
                if os.path.isfile(local_path):
                    filename = os.path.basename(local_path)
                    remote_path = f"{remote_dir.rstrip('/')}/{filename}"

                    # Check if remote file exists
                    if sftp_manager.exists(remote_path):
                        local_stat = os.stat(local_path)
                        local_date = datetime.fromtimestamp(local_stat.st_mtime)
                        local_size = local_stat.st_size

                        try:
                            remote_metadata = sftp_manager.get_file_info(remote_path)
                            remote_date = remote_metadata.modified
                            remote_size = remote_metadata.size

                            conflicts.append({
                                'filename': filename,
                                'source_path': local_path,
                                'dest_path': remote_path,
                                'source_size': local_size,
                                'dest_size': remote_size,
                                'source_date': local_date,
                                'dest_date': remote_date
                            })
                        except Exception as e:
                            logger.warning(f"Could not get remote file info: {e}")

        except Exception as e:
            logger.error(f"Conflict check failed: {e}")

        return conflicts

    @staticmethod
    def check_download_conflicts(remote_paths: List[str], local_dir: str,
                                sftp_manager) -> List[Dict]:
        """
        Check for file conflicts during download.

        Args:
            remote_paths: List of remote file paths to transfer
            local_dir: Local destination directory
            sftp_manager: SFTPManager instance

        Returns:
            List of conflict dictionaries (empty if no conflicts)
        """
        conflicts = []

        try:
            import os
            from pathlib import Path
            from datetime import datetime

            for remote_path in remote_paths:
                filename = remote_path.split('/')[-1]
                local_path = os.path.join(local_dir, filename)

                # Check if local file exists
                if os.path.exists(local_path):
                    local_stat = os.stat(local_path)
                    local_date = datetime.fromtimestamp(local_stat.st_mtime)
                    local_size = local_stat.st_size

                    try:
                        remote_metadata = sftp_manager.get_file_info(remote_path)
                        remote_date = remote_metadata.modified
                        remote_size = remote_metadata.size

                        conflicts.append({
                            'filename': filename,
                            'source_path': remote_path,
                            'dest_path': local_path,
                            'source_size': remote_size,
                            'dest_size': local_size,
                            'source_date': remote_date,
                            'dest_date': local_date
                        })
                    except Exception as e:
                        logger.warning(f"Could not get remote file info: {e}")

        except Exception as e:
            logger.error(f"Download conflict check failed: {e}")

        return conflicts
