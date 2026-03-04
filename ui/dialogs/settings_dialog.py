"""Settings / Preferences dialog — tabbed UI for appearance, connection
defaults, job manager, and file transfer configuration."""

import logging
import os
from pathlib import Path
from typing import Optional
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QPushButton, QLabel, QComboBox, QSpinBox, QLineEdit,
    QCheckBox, QGroupBox, QFormLayout, QFileDialog, QMessageBox,
    QDoubleSpinBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QFont

from transfpro.config.settings import Settings

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """
    Application settings and preferences dialog.

    Provides organized settings management through multiple tabs:
    - General: Theme, notifications, system tray options
    - Connection: SSH timeouts, keepalive, auto-reconnect
    - Job Manager: Refresh intervals, default job parameters
    - File Transfer: Concurrent transfers, file browser options
    """

    settings_changed = pyqtSignal()  # Emitted when settings are saved

    def __init__(self, settings: Settings, parent=None):
        """
        Initialize settings dialog.

        Args:
            settings: Settings object to manage
            parent: Parent widget
        """
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        self.setMinimumSize(700, 600)
        self.setModal(True)

        # Store original values for cancel handling
        self._original_settings = {}

        self._setup_ui()
        self.load_settings()

    def _setup_ui(self):
        """Setup dialog user interface."""
        main_layout = QVBoxLayout()

        # Tab widget for settings categories
        self.tab_widget = QTabWidget()

        # Create tabs
        self.tab_widget.addTab(self._create_general_tab(), "General")
        self.tab_widget.addTab(self._create_connection_tab(), "Connection")
        self.tab_widget.addTab(self._create_job_manager_tab(), "Job Manager")
        self.tab_widget.addTab(self._create_file_transfer_tab(), "File Transfer")

        main_layout.addWidget(self.tab_widget)

        # Button bar
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        restore_btn = QPushButton("Restore Defaults")
        restore_btn.clicked.connect(self.restore_defaults)
        button_layout.addWidget(restore_btn)

        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self.apply_settings)
        button_layout.addWidget(apply_btn)

        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(ok_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)

    def _create_general_tab(self) -> QWidget:
        """Create General settings tab."""
        widget = QWidget()
        outer = QVBoxLayout()

        layout = QFormLayout()

        # Theme selection
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "Light"])
        layout.addRow("Theme:", self.theme_combo)

        # Start minimized to tray
        self.minimize_tray_checkbox = QCheckBox("Start minimized to system tray")
        layout.addRow(self.minimize_tray_checkbox)

        # Show notifications
        self.notifications_checkbox = QCheckBox("Show desktop notifications")
        layout.addRow(self.notifications_checkbox)

        # Enable sound alerts
        self.sound_alerts_checkbox = QCheckBox("Enable sound alerts")
        layout.addRow(self.sound_alerts_checkbox)

        # Confirm before exit
        self.confirm_exit_checkbox = QCheckBox("Confirm before exiting application")
        self.confirm_exit_checkbox.setChecked(True)
        layout.addRow(self.confirm_exit_checkbox)

        # Font size
        self.font_size_spinbox = QSpinBox()
        self.font_size_spinbox.setMinimum(8)
        self.font_size_spinbox.setMaximum(24)
        self.font_size_spinbox.setSuffix(" pt")
        self.font_size_spinbox.setValue(13)
        self.font_size_spinbox.setToolTip(
            "Adjust the overall UI font size. Takes effect after Apply."
        )
        layout.addRow("UI Font Size:", self.font_size_spinbox)

        outer.addLayout(layout)
        outer.addStretch()
        widget.setLayout(outer)
        return widget

    def _create_connection_tab(self) -> QWidget:
        """Create Connection settings tab."""
        widget = QWidget()
        outer = QVBoxLayout()
        layout = QFormLayout()

        # SSH timeout
        self.ssh_timeout_spinbox = QSpinBox()
        self.ssh_timeout_spinbox.setMinimum(5)
        self.ssh_timeout_spinbox.setMaximum(120)
        self.ssh_timeout_spinbox.setSuffix(" seconds")
        self.ssh_timeout_spinbox.setValue(30)
        layout.addRow("SSH Connection Timeout:", self.ssh_timeout_spinbox)

        # Keepalive interval
        self.keepalive_spinbox = QSpinBox()
        self.keepalive_spinbox.setMinimum(10)
        self.keepalive_spinbox.setMaximum(300)
        self.keepalive_spinbox.setSuffix(" seconds")
        self.keepalive_spinbox.setValue(60)
        layout.addRow("Keepalive Interval:", self.keepalive_spinbox)

        # Auto-reconnect
        self.auto_reconnect_checkbox = QCheckBox("Auto-reconnect on connection loss")
        self.auto_reconnect_checkbox.setChecked(True)
        layout.addRow(self.auto_reconnect_checkbox)

        # Remember passwords
        self.remember_passwords_checkbox = QCheckBox(
            "Remember passwords"
        )
        layout.addRow(self.remember_passwords_checkbox)

        # Connection retry attempts
        self.retry_attempts_spinbox = QSpinBox()
        self.retry_attempts_spinbox.setMinimum(1)
        self.retry_attempts_spinbox.setMaximum(10)
        self.retry_attempts_spinbox.setValue(3)
        layout.addRow("Connection Retry Attempts:", self.retry_attempts_spinbox)

        outer.addLayout(layout)
        outer.addStretch()
        widget.setLayout(outer)
        return widget

    def _create_job_manager_tab(self) -> QWidget:
        """Create Job Manager settings tab."""
        widget = QWidget()
        outer = QVBoxLayout()
        layout = QFormLayout()

        # Auto-refresh interval
        self.job_refresh_spinbox = QSpinBox()
        self.job_refresh_spinbox.setMinimum(5)
        self.job_refresh_spinbox.setMaximum(300)
        self.job_refresh_spinbox.setSuffix(" seconds")
        self.job_refresh_spinbox.setValue(30)
        layout.addRow("Auto-refresh Interval:", self.job_refresh_spinbox)

        # Default partition
        self.default_partition_line = QLineEdit()
        self.default_partition_line.setPlaceholderText("e.g., gpu, cpu, normal")
        layout.addRow("Default Partition:", self.default_partition_line)

        # Default time limit
        self.default_time_spinbox = QSpinBox()
        self.default_time_spinbox.setMinimum(1)
        self.default_time_spinbox.setMaximum(1440)
        self.default_time_spinbox.setSuffix(" minutes")
        self.default_time_spinbox.setValue(60)
        layout.addRow("Default Time Limit:", self.default_time_spinbox)

        # Default CPUs
        self.default_cpus_spinbox = QSpinBox()
        self.default_cpus_spinbox.setMinimum(1)
        self.default_cpus_spinbox.setMaximum(256)
        self.default_cpus_spinbox.setValue(4)
        layout.addRow("Default CPUs per Task:", self.default_cpus_spinbox)

        # Default memory
        self.default_memory_spinbox = QSpinBox()
        self.default_memory_spinbox.setMinimum(256)
        self.default_memory_spinbox.setMaximum(512000)
        self.default_memory_spinbox.setSuffix(" MB")
        self.default_memory_spinbox.setValue(4096)
        layout.addRow("Default Memory per Task:", self.default_memory_spinbox)

        # Notification on completion
        self.job_complete_notify = QCheckBox("Notify on job completion")
        self.job_complete_notify.setChecked(True)
        layout.addRow(self.job_complete_notify)

        # Notification on failure
        self.job_failure_notify = QCheckBox("Notify on job failure")
        self.job_failure_notify.setChecked(True)
        layout.addRow(self.job_failure_notify)

        outer.addLayout(layout)
        outer.addStretch()
        widget.setLayout(outer)
        return widget

    def _create_file_transfer_tab(self) -> QWidget:
        """Create File Transfer settings tab."""
        widget = QWidget()
        outer = QVBoxLayout()
        layout = QFormLayout()

        # Max concurrent transfers
        self.max_transfers_spinbox = QSpinBox()
        self.max_transfers_spinbox.setMinimum(1)
        self.max_transfers_spinbox.setMaximum(20)
        self.max_transfers_spinbox.setValue(4)
        layout.addRow("Max Concurrent Transfers:", self.max_transfers_spinbox)

        # Show hidden files
        self.show_hidden_checkbox = QCheckBox("Show hidden files by default")
        layout.addRow(self.show_hidden_checkbox)

        # Confirm overwrite
        self.confirm_overwrite_checkbox = QCheckBox("Confirm before overwriting files")
        self.confirm_overwrite_checkbox.setChecked(True)
        layout.addRow(self.confirm_overwrite_checkbox)

        # Default local directory
        local_dir_layout = QHBoxLayout()
        self.default_local_dir = QLineEdit()
        self.default_local_dir.setPlaceholderText("Leave empty for user home directory")
        browse_local_btn = QPushButton("Browse...")
        browse_local_btn.setMaximumWidth(80)
        browse_local_btn.clicked.connect(self._browse_local_directory)
        local_dir_layout.addWidget(self.default_local_dir)
        local_dir_layout.addWidget(browse_local_btn)
        layout.addRow("Default Local Directory:", local_dir_layout)

        # Default remote directory
        self.default_remote_dir = QLineEdit()
        self.default_remote_dir.setPlaceholderText("e.g., /home/username")
        layout.addRow("Default Remote Directory:", self.default_remote_dir)

        # Buffer size
        self.buffer_size_spinbox = QSpinBox()
        self.buffer_size_spinbox.setMinimum(1024)
        self.buffer_size_spinbox.setMaximum(10240)
        self.buffer_size_spinbox.setSingleStep(1024)
        self.buffer_size_spinbox.setSuffix(" KB")
        self.buffer_size_spinbox.setValue(4096)
        layout.addRow("Transfer Buffer Size:", self.buffer_size_spinbox)

        outer.addLayout(layout)
        outer.addStretch()
        widget.setLayout(outer)
        return widget

    def _browse_local_directory(self):
        """Open directory browser for local directory selection."""
        current_dir = self.default_local_dir.text() or str(Path.home())
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Default Local Directory",
            current_dir
        )
        if directory:
            self.default_local_dir.setText(directory)

    def load_settings(self):
        """Load settings from Settings object into form."""
        try:
            # General tab
            theme = self.settings.get_theme()
            self.theme_combo.setCurrentText("Dark" if theme == "dark" else "Light")

            self.minimize_tray_checkbox.setChecked(
                self.settings.get_value("appearance/minimize_to_tray", False)
            )
            self.notifications_checkbox.setChecked(
                self.settings.get_value("notifications/enabled", True)
            )
            self.sound_alerts_checkbox.setChecked(
                self.settings.get_value("notifications/sound_enabled", True)
            )
            self.font_size_spinbox.setValue(
                self.settings.get_value("appearance/font_size", 13)
            )

            # Connection tab
            self.ssh_timeout_spinbox.setValue(
                self.settings.get_value("connection/ssh_timeout", 30)
            )
            self.keepalive_spinbox.setValue(
                self.settings.get_value("connection/keepalive_interval", 60)
            )
            self.auto_reconnect_checkbox.setChecked(
                self.settings.get_value("connection/auto_reconnect", True)
            )
            self.remember_passwords_checkbox.setChecked(
                self.settings.get_remember_passwords()
            )
            self.retry_attempts_spinbox.setValue(
                self.settings.get_value("connection/retry_attempts", 3)
            )

            # Job Manager tab
            self.job_refresh_spinbox.setValue(
                self.settings.get_auto_refresh_interval()
            )
            self.default_partition_line.setText(
                self.settings.get_value("jobs/default_partition", "")
            )
            self.default_time_spinbox.setValue(
                self.settings.get_value("jobs/default_time_limit", 60)
            )
            self.default_cpus_spinbox.setValue(
                self.settings.get_value("jobs/default_cpus", 4)
            )
            self.default_memory_spinbox.setValue(
                self.settings.get_value("jobs/default_memory_mb", 4096)
            )
            self.job_complete_notify.setChecked(
                self.settings.get_value("jobs/notify_completion", True)
            )
            self.job_failure_notify.setChecked(
                self.settings.get_value("jobs/notify_failure", True)
            )

            # File Transfer tab
            self.max_transfers_spinbox.setValue(
                self.settings.get_max_concurrent_transfers()
            )
            self.show_hidden_checkbox.setChecked(
                self.settings.get_show_hidden_files()
            )
            self.confirm_overwrite_checkbox.setChecked(
                self.settings.get_value("files/confirm_overwrite", True)
            )
            self.default_local_dir.setText(
                self.settings.get_last_download_directory()
            )
            self.default_remote_dir.setText(
                self.settings.get_value("files/default_remote_dir", "")
            )
            self.buffer_size_spinbox.setValue(
                self.settings.get_value("transfers/buffer_size_kb", 4096)
            )

            logger.info("Settings loaded successfully")

        except Exception as e:
            logger.error(f"Error loading settings: {e}")
            QMessageBox.warning(self, "Load Error", f"Failed to load settings: {str(e)}")

    def apply_settings(self):
        """Save form values to Settings object."""
        try:
            # General tab
            theme = "dark" if self.theme_combo.currentText() == "Dark" else "light"
            self.settings.set_theme(theme)
            self.settings.set_value(
                "appearance/minimize_to_tray",
                self.minimize_tray_checkbox.isChecked()
            )
            self.settings.set_value(
                "notifications/enabled",
                self.notifications_checkbox.isChecked()
            )
            self.settings.set_value(
                "notifications/sound_enabled",
                self.sound_alerts_checkbox.isChecked()
            )
            self.settings.set_value(
                "appearance/font_size",
                self.font_size_spinbox.value()
            )
            # Apply font size immediately to running application
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                font = app.font()
                font.setPointSize(self.font_size_spinbox.value())
                app.setFont(font)

            # Connection tab
            self.settings.set_value(
                "connection/ssh_timeout",
                self.ssh_timeout_spinbox.value()
            )
            self.settings.set_value(
                "connection/keepalive_interval",
                self.keepalive_spinbox.value()
            )
            self.settings.set_value(
                "connection/auto_reconnect",
                self.auto_reconnect_checkbox.isChecked()
            )
            self.settings.set_remember_passwords(
                self.remember_passwords_checkbox.isChecked()
            )
            self.settings.set_value(
                "connection/retry_attempts",
                self.retry_attempts_spinbox.value()
            )

            # Job Manager tab
            self.settings.set_auto_refresh_interval(
                self.job_refresh_spinbox.value()
            )
            self.settings.set_value(
                "jobs/default_partition",
                self.default_partition_line.text()
            )
            self.settings.set_value(
                "jobs/default_time_limit",
                self.default_time_spinbox.value()
            )
            self.settings.set_value(
                "jobs/default_cpus",
                self.default_cpus_spinbox.value()
            )
            self.settings.set_value(
                "jobs/default_memory_mb",
                self.default_memory_spinbox.value()
            )
            self.settings.set_value(
                "jobs/notify_completion",
                self.job_complete_notify.isChecked()
            )
            self.settings.set_value(
                "jobs/notify_failure",
                self.job_failure_notify.isChecked()
            )

            # File Transfer tab
            self.settings.set_max_concurrent_transfers(
                self.max_transfers_spinbox.value()
            )
            self.settings.set_show_hidden_files(
                self.show_hidden_checkbox.isChecked()
            )
            self.settings.set_value(
                "files/confirm_overwrite",
                self.confirm_overwrite_checkbox.isChecked()
            )
            self.settings.set_last_download_directory(
                self.default_local_dir.text()
            )
            self.settings.set_value(
                "files/default_remote_dir",
                self.default_remote_dir.text()
            )
            self.settings.set_value(
                "transfers/buffer_size_kb",
                self.buffer_size_spinbox.value()
            )

            self.settings.sync()
            self.settings_changed.emit()
            logger.info("Settings applied successfully")
            QMessageBox.information(self, "Success", "Settings saved successfully.")

        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            QMessageBox.critical(self, "Save Error", f"Failed to save settings: {str(e)}")

    def restore_defaults(self):
        """Reset all settings to default values."""
        reply = QMessageBox.question(
            self,
            "Restore Defaults",
            "Are you sure you want to reset all settings to their default values?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Reset all form values to defaults
            self.theme_combo.setCurrentText("Dark")
            self.minimize_tray_checkbox.setChecked(False)
            self.notifications_checkbox.setChecked(True)
            self.sound_alerts_checkbox.setChecked(True)
            self.font_size_spinbox.setValue(13)

            self.ssh_timeout_spinbox.setValue(30)
            self.keepalive_spinbox.setValue(60)
            self.auto_reconnect_checkbox.setChecked(True)
            self.remember_passwords_checkbox.setChecked(False)
            self.retry_attempts_spinbox.setValue(3)

            self.job_refresh_spinbox.setValue(30)
            self.default_partition_line.clear()
            self.default_time_spinbox.setValue(60)
            self.default_cpus_spinbox.setValue(4)
            self.default_memory_spinbox.setValue(4096)
            self.job_complete_notify.setChecked(True)
            self.job_failure_notify.setChecked(True)

            self.max_transfers_spinbox.setValue(3)
            self.show_hidden_checkbox.setChecked(False)
            self.confirm_overwrite_checkbox.setChecked(True)
            self.default_local_dir.clear()
            self.default_remote_dir.clear()
            self.buffer_size_spinbox.setValue(4096)

            logger.info("Settings restored to defaults")
