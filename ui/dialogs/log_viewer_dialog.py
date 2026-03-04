"""
Full-screen log viewer with search and live tail.

This module provides a LogViewerDialog for viewing job logs with features
including search, auto-scroll, and live tail updates.
"""

import logging
from typing import Optional
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QLineEdit,
    QPushButton, QCheckBox, QSpinBox, QLabel, QStatusBar, QToolBar,
    QSizePolicy
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QTextCursor

from transfpro.workers.log_tail_worker import LogTailWorker
from transfpro.core.ssh_manager import SSHManager

logger = logging.getLogger(__name__)


class _LogLoadWorker(QThread):
    """Fetches log content in a background thread so the dialog shows instantly."""

    loaded = pyqtSignal(str, bool)  # content, success

    def __init__(self, ssh_manager, log_path):
        super().__init__()
        self._ssh = ssh_manager
        self._log_path = log_path

    def run(self):
        try:
            stdout, _, code = self._ssh.execute_command(
                f"tail -1000 {self._log_path}"
            )
            if code == 0:
                self.loaded.emit(stdout, True)
            else:
                self.loaded.emit(
                    f"Error loading log: {self._log_path} not found", False
                )
        except Exception as e:
            self.loaded.emit(f"Error loading log: {e}", False)


class LogViewerDialog(QDialog):
    """Full-screen log viewer with search, auto-scroll, and live tail."""

    def __init__(self, ssh_manager: SSHManager, job_id: str,
                 log_path: str, parent=None):
        """
        Initialize the log viewer dialog.

        Args:
            ssh_manager: SSHManager instance for remote file access
            job_id: Job ID for window title
            log_path: Remote path to log file
            parent: Parent widget
        """
        super().__init__(parent)
        self.ssh_manager = ssh_manager
        self.job_id = job_id
        self.log_path = log_path
        self.tail_worker = None
        self.tail_thread = None
        self.search_index = 0

        self.setWindowTitle(f"Log Viewer - Job {job_id}")
        self.resize(1000, 700)
        self._setup_ui()
        self._setup_connections()
        self._load_log()

    def _setup_ui(self):
        """Set up the UI layout."""
        layout = QVBoxLayout()

        # Toolbar
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)

        # Main text area
        self.log_text = QPlainTextEdit()
        font = QFont("Courier New", 10)
        self.log_text.setFont(font)
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

        # Status bar
        self.status_bar = QStatusBar()
        layout.addWidget(self.status_bar)

        self.setLayout(layout)

    def _create_toolbar(self) -> QToolBar:
        """
        Create the toolbar.

        Returns:
            QToolBar widget
        """
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))

        # Search input
        toolbar.addWidget(QLabel("  Search: "))
        self.search_input = QLineEdit()
        self.search_input.setMaximumWidth(200)
        self.search_input.setPlaceholderText("Find text...")
        self.search_input.returnPressed.connect(self._find_next)
        toolbar.addWidget(self.search_input)

        # Find buttons
        find_next_btn = QPushButton("Find Next")
        find_next_btn.setMaximumWidth(100)
        find_next_btn.clicked.connect(self._find_next)
        toolbar.addWidget(find_next_btn)

        find_prev_btn = QPushButton("Find Prev")
        find_prev_btn.setMaximumWidth(100)
        find_prev_btn.clicked.connect(self._find_previous)
        toolbar.addWidget(find_prev_btn)

        toolbar.addSeparator()

        # Auto-scroll
        self.auto_scroll_check = QCheckBox("Auto-scroll")
        self.auto_scroll_check.setChecked(True)
        toolbar.addWidget(self.auto_scroll_check)

        # Live tail
        self.live_tail_check = QCheckBox("Live Tail")
        self.live_tail_check.setChecked(False)
        self.live_tail_check.toggled.connect(self._on_live_tail_toggled)
        toolbar.addWidget(self.live_tail_check)

        # Refresh interval
        toolbar.addWidget(QLabel("  Refresh (s): "))
        self.refresh_interval = QSpinBox()
        self.refresh_interval.setMinimum(1)
        self.refresh_interval.setMaximum(60)
        self.refresh_interval.setValue(5)
        self.refresh_interval.setMaximumWidth(60)
        toolbar.addWidget(self.refresh_interval)

        # Font size
        toolbar.addWidget(QLabel("  Font Size: "))
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setMinimum(8)
        self.font_size_spin.setMaximum(24)
        self.font_size_spin.setValue(10)
        self.font_size_spin.setMaximumWidth(60)
        self.font_size_spin.valueChanged.connect(self._on_font_size_changed)
        toolbar.addWidget(self.font_size_spin)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setMaximumWidth(100)
        close_btn.clicked.connect(self.accept)
        toolbar.addWidget(close_btn)

        return toolbar

    def _setup_connections(self):
        """Set up signal/slot connections."""
        pass

    def _load_log(self):
        """Load log content in a background thread so the dialog shows instantly."""
        self.status_bar.showMessage("Loading log file...")
        self.log_text.setPlainText("Loading...")

        self._load_worker = _LogLoadWorker(self.ssh_manager, self.log_path)
        self._load_worker.loaded.connect(self._on_log_loaded)
        self._load_worker.start()

    def _on_log_loaded(self, content: str, success: bool):
        """Called when the background log fetch finishes."""
        self.log_text.setPlainText(content)
        self._update_status()
        if success:
            self.status_bar.showMessage("Log loaded successfully")
            # Auto-scroll to bottom
            scrollbar = self.log_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        else:
            self.status_bar.showMessage("Failed to load log")

    def _find_next(self):
        """Find next occurrence of search text."""
        search_text = self.search_input.text()
        if not search_text:
            return

        cursor = self.log_text.textCursor()
        if cursor.hasSelection():
            cursor.setPosition(cursor.selectionEnd())
        else:
            cursor.setPosition(0)

        self.log_text.setTextCursor(cursor)
        found = self.log_text.find(search_text)
        self._update_status()

    def _find_previous(self):
        """Find previous occurrence of search text."""
        search_text = self.search_input.text()
        if not search_text:
            return

        cursor = self.log_text.textCursor()
        if cursor.hasSelection():
            cursor.setPosition(cursor.selectionStart())
        else:
            cursor.setPosition(self.log_text.document().characterCount())

        # Find backwards
        found = False
        while cursor.position() >= 0:
            cursor.movePosition(
                QTextCursor.StartOfBlock,
                QTextCursor.MoveAnchor
            )
            cursor.movePosition(
                QTextCursor.EndOfBlock,
                QTextCursor.KeepAnchor
            )

            if search_text.lower() in cursor.selectedText().lower():
                found = True
                break

            cursor.movePosition(QTextCursor.PreviousBlock)

        if found:
            self.log_text.setTextCursor(cursor)

        self._update_status()

    def _on_live_tail_toggled(self, checked: bool):
        """
        Handle live tail toggle.

        Args:
            checked: Whether live tail is enabled
        """
        if checked:
            self._start_live_tail()
        else:
            self._stop_live_tail()

    def _start_live_tail(self):
        """Start live tail of log file."""
        # Guard: don't start a second tail thread
        if self.tail_thread and self.tail_thread.isRunning():
            return

        self.tail_thread = QThread()
        self.tail_worker = LogTailWorker(
            self.ssh_manager,
            self.job_id,
            self.log_path,
            poll_interval=self.refresh_interval.value()
        )
        self.tail_worker.moveToThread(self.tail_thread)

        self.tail_worker.new_content.connect(self._on_new_log_content)
        self.tail_thread.started.connect(self.tail_worker.do_work)
        self.tail_worker.finished.connect(self.tail_thread.quit)

        self.tail_thread.start()
        self.status_bar.showMessage("Live tail enabled")

    def _stop_live_tail(self):
        """Stop live tail of log file."""
        if self.tail_worker:
            self.tail_worker.stop()
            self.tail_worker.cancel()

        if self.tail_thread:
            self.tail_thread.quit()
            if not self.tail_thread.wait(5000):
                self.tail_thread.terminate()
                self.tail_thread.wait(2000)

        self.tail_thread = None
        self.tail_worker = None
        self.status_bar.showMessage("Live tail disabled")

    def _on_new_log_content(self, job_id: str, content: str):
        """
        Handle new log content from live tail.

        Args:
            job_id: Job identifier
            content: New log lines
        """
        if not content:
            return

        # Trim document if it exceeds 10,000 lines to prevent memory issues
        doc = self.log_text.document()
        if doc.blockCount() > 10000:
            cursor = QTextCursor(doc)
            cursor.movePosition(QTextCursor.Start)
            # Select the first 5000 lines and remove them
            for _ in range(5000):
                cursor.movePosition(QTextCursor.NextBlock, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()

        # appendPlainText is much faster than setPlainText for large docs
        self.log_text.appendPlainText(content)

        if self.auto_scroll_check.isChecked():
            scrollbar = self.log_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        self._update_status()

    def _on_tail_error(self, error: str):
        """
        Handle live tail error.

        Args:
            error: Error message
        """
        logger.error(f"Live tail error: {error}")
        self.status_bar.showMessage(f"Error: {error}")

    def _on_font_size_changed(self, size: int):
        """
        Handle font size change.

        Args:
            size: New font size
        """
        font = self.log_text.font()
        font.setPointSize(size)
        self.log_text.setFont(font)

    def _update_status(self):
        """Update status bar with log info."""
        doc = self.log_text.document()
        line_count = doc.blockCount()
        char_count = doc.characterCount()

        self.status_bar.showMessage(
            f"Lines: {line_count:,} | Characters: {char_count:,}"
        )

    def closeEvent(self, event):
        """
        Handle window close.

        Args:
            event: Close event
        """
        self._stop_live_tail()
        if hasattr(self, '_load_worker') and self._load_worker.isRunning():
            self._load_worker.quit()
            self._load_worker.wait(2000)
        super().closeEvent(event)
