"""
Professional job table widget with sorting, filtering, and color-coded status.

This module provides the JobTableWidget for displaying SLURM jobs in a table
with advanced features including sorting, filtering, context menus, and status
color coding.
"""

import logging
from typing import Optional, List
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QComboBox, QLabel, QProgressBar, QMenu, QMessageBox,
    QApplication, QHeaderView
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QIcon, QBrush

from transfpro.core.slurm_manager import JobInfo
from transfpro.ui.widgets.search_bar import SearchBar

logger = logging.getLogger(__name__)

# State foreground colors (text color for the STATE cell)
STATE_FG_COLORS = {
    'RUNNING': QColor(76, 230, 100),      # Green
    'PENDING': QColor(255, 165, 0),        # Orange
    'COMPLETED': QColor(80, 170, 255),     # Blue
    'FAILED': QColor(255, 80, 70),         # Red
    'CANCELLED': QColor(158, 158, 158),    # Grey
    'TIMEOUT': QColor(255, 120, 50),       # Dark orange
    'STOPPED': QColor(233, 80, 120),       # Pink
}

# Subtle row tint per state (very translucent)
STATE_ROW_TINTS = {
    'RUNNING': QColor(76, 230, 100, 22),
    'PENDING': QColor(255, 165, 0, 18),
    'COMPLETED': QColor(80, 170, 255, 12),
    'FAILED': QColor(255, 80, 70, 15),
    'CANCELLED': QColor(158, 158, 158, 10),
    'TIMEOUT': QColor(255, 120, 50, 15),
    'STOPPED': QColor(233, 80, 120, 12),
}

# Default text color for non-state cells (light gray for dark theme)
_DEFAULT_FG = QColor(232, 232, 239)  # #e8e8ef

# Cache fonts
_BOLD_FONT = QFont()
_BOLD_FONT.setBold(True)


class JobTableWidget(QWidget):
    """Table showing SLURM jobs with sorting, filtering, and color coding."""

    job_selected = pyqtSignal(object)  # JobInfo
    job_double_clicked = pyqtSignal(object)  # JobInfo
    resubmit_requested = pyqtSignal(object)  # JobInfo

    # Sort keys per column index (attribute name or callable)
    _SORT_KEYS = {
        0: lambda j: int(j.job_id) if j.job_id.isdigit() else j.job_id,
        1: lambda j: j.name.lower(),
        2: lambda j: j.state.upper() if j.state else '',
        3: lambda j: (j.queue or '').lower(),
        4: lambda j: j.nodes,
        5: lambda j: j.cpus,
        6: lambda j: j.elapsed or '',                     # Time Used/Limit
        7: lambda j: j.metadata.get('progress', 0),       # Progress %
        8: lambda j: j.metadata.get('ns_per_day', 0),     # ns/day
        9: lambda j: j.submission_time.timestamp() if j.submission_time else 0,
    }

    def __init__(self, parent=None):
        """
        Initialize the job table widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.jobs: List[JobInfo] = []
        self.filtered_jobs: List[JobInfo] = []
        self._sort_column = 0
        self._sort_order = Qt.DescendingOrder  # newest first by default
        self._setup_ui()
        self._setup_connections()

    def _setup_ui(self):
        """Set up the UI layout."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Search/filter bar
        search_filters = ["All", "Running", "Pending", "Completed", "Failed", "Cancelled"]
        self.search_bar = SearchBar(
            placeholder="Search by job name or ID...",
            filters=search_filters
        )
        layout.addWidget(self.search_bar)

        # Info bar
        info_layout = QHBoxLayout()
        self.job_count_label = QLabel("Showing 0 of 0 jobs")
        info_layout.addWidget(self.job_count_label)
        info_layout.addStretch()

        refresh_button = QPushButton("Refresh")
        refresh_button.setMaximumWidth(100)
        refresh_button.clicked.connect(self._on_refresh_clicked)
        info_layout.addWidget(refresh_button)

        layout.addLayout(info_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "Job ID", "Name", "State", "Partition", "Nodes",
            "CPUs", "Time Used/Limit", "Progress", "ns/day", "Submit Time"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        # Enable multi-row selection
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.setAlternatingRowColors(False)  # We do our own row coloring
        self.table.setColumnWidth(0, 80)   # Job ID
        self.table.setColumnWidth(1, 120)  # Name
        self.table.setColumnWidth(2, 100)  # State
        self.table.setColumnWidth(3, 100)  # Partition
        self.table.setColumnWidth(4, 70)   # Nodes
        self.table.setColumnWidth(5, 70)   # CPUs
        self.table.setColumnWidth(6, 200)  # Time
        self.table.setColumnWidth(7, 120)  # Progress
        self.table.setColumnWidth(8, 80)   # ns/day
        layout.addWidget(self.table)

        self.setLayout(layout)

    def _setup_connections(self):
        """Set up signal/slot connections."""
        self.search_bar.search_changed.connect(self._apply_filters)
        self.search_bar.filter_changed.connect(self._apply_filters)
        self.table.itemSelectionChanged.connect(self._on_job_selected)
        self.table.itemDoubleClicked.connect(self._on_job_double_clicked)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._create_context_menu)

        # Column header click → sort
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._on_header_clicked)
        header.setSortIndicatorShown(True)
        header.setSortIndicator(self._sort_column, self._sort_order)

    def _on_header_clicked(self, col: int):
        """Sort jobs by the clicked column."""
        if col == self._sort_column:
            # Toggle order
            self._sort_order = (
                Qt.AscendingOrder if self._sort_order == Qt.DescendingOrder
                else Qt.DescendingOrder
            )
        else:
            self._sort_column = col
            self._sort_order = Qt.AscendingOrder

        header = self.table.horizontalHeader()
        header.setSortIndicator(self._sort_column, self._sort_order)
        self._apply_filters()  # Re-filter + sort

    def update_jobs(self, jobs: List[JobInfo]):
        """
        Populate table with job data and apply current filters.

        Args:
            jobs: List of JobInfo objects to display
        """
        self.jobs = jobs
        self._apply_filters()

    def _apply_filters(self):
        """Filter displayed jobs based on search text and state filter."""
        search_text = self.search_bar.get_search_text().lower()
        state_filter = self.search_bar.get_filter_value() or "All"

        # Filter jobs
        self.filtered_jobs = []
        for job in self.jobs:
            # State filter (case-insensitive comparison)
            if state_filter != "All" and job.state.upper() != state_filter.upper():
                continue

            # Text search (job ID or name)
            if search_text:
                if (search_text not in job.job_id.lower() and
                    search_text not in job.name.lower()):
                    continue

            self.filtered_jobs.append(job)

        # Sort filtered jobs
        sort_key = self._SORT_KEYS.get(self._sort_column)
        if sort_key:
            try:
                self.filtered_jobs.sort(
                    key=sort_key,
                    reverse=(self._sort_order == Qt.DescendingOrder)
                )
            except Exception:
                pass  # Fallback: keep original order

        # Update table
        self._populate_table()
        self._update_count_label()

    def _populate_table(self):
        """Populate the table with filtered jobs."""
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.filtered_jobs))

        for row, job in enumerate(self.filtered_jobs):
            state_upper = job.state.upper() if job.state else ""
            row_tint = STATE_ROW_TINTS.get(state_upper)
            state_fg = STATE_FG_COLORS.get(state_upper, QColor(158, 158, 158))

            # Job ID
            job_id_item = QTableWidgetItem(job.job_id)
            job_id_item.setData(Qt.UserRole, job)
            job_id_item.setForeground(_DEFAULT_FG)
            if row_tint:
                job_id_item.setBackground(row_tint)
            self.table.setItem(row, 0, job_id_item)

            # Name
            name_item = QTableWidgetItem(job.name)
            name_item.setTextAlignment(Qt.AlignCenter)
            name_item.setForeground(_DEFAULT_FG)
            if row_tint:
                name_item.setBackground(row_tint)
            self.table.setItem(row, 1, name_item)

            # State (colored text, bold)
            state_item = QTableWidgetItem(state_upper)
            state_item.setForeground(state_fg)
            state_item.setFont(_BOLD_FONT)
            if row_tint:
                state_item.setBackground(row_tint)
            self.table.setItem(row, 2, state_item)

            # Partition
            partition_item = QTableWidgetItem(job.queue or "-")
            partition_item.setForeground(_DEFAULT_FG)
            if row_tint:
                partition_item.setBackground(row_tint)
            self.table.setItem(row, 3, partition_item)

            # Nodes
            nodes_item = QTableWidgetItem(str(job.nodes))
            nodes_item.setTextAlignment(Qt.AlignCenter)
            nodes_item.setForeground(_DEFAULT_FG)
            if row_tint:
                nodes_item.setBackground(row_tint)
            self.table.setItem(row, 4, nodes_item)

            # CPUs
            cpus_item = QTableWidgetItem(str(job.cpus))
            cpus_item.setTextAlignment(Qt.AlignCenter)
            cpus_item.setForeground(_DEFAULT_FG)
            if row_tint:
                cpus_item.setBackground(row_tint)
            self.table.setItem(row, 5, cpus_item)

            # Time Used / Limit — compute elapsed from start_time if missing
            elapsed = job.elapsed or ""
            if not elapsed and job.start_time and job.state and job.state.upper() == "RUNNING":
                from datetime import datetime
                secs = int((datetime.now() - job.start_time).total_seconds())
                if secs > 0:
                    d, r = divmod(secs, 86400)
                    h, r = divmod(r, 3600)
                    m, s = divmod(r, 60)
                    elapsed = f"{d}-{h:02d}:{m:02d}:{s:02d}" if d else f"{h}:{m:02d}:{s:02d}"
            time_limit = job.time_limit or ""
            if elapsed and time_limit:
                time_text = f"{elapsed} / {time_limit}"
            elif time_limit:
                time_text = f"— / {time_limit}"
            elif elapsed:
                time_text = elapsed
            else:
                time_text = "—"
            time_item = QTableWidgetItem(time_text)
            time_item.setForeground(_DEFAULT_FG)
            if row_tint:
                time_item.setBackground(row_tint)
            self.table.setItem(row, 6, time_item)

            # Progress bar — reuse existing widget if available
            existing_bar = self.table.cellWidget(row, 7)
            if isinstance(existing_bar, QProgressBar):
                existing_bar.setValue(self._calculate_progress(job))
            else:
                progress_bar = QProgressBar()
                progress_bar.setMaximum(100)
                progress_bar.setValue(self._calculate_progress(job))
                progress_bar.setTextVisible(True)
                self.table.setCellWidget(row, 7, progress_bar)

            # ns/day (placeholder for performance metric)
            ns_day_item = QTableWidgetItem("-")
            ns_day_item.setTextAlignment(Qt.AlignCenter)
            ns_day_item.setForeground(_DEFAULT_FG)
            if row_tint:
                ns_day_item.setBackground(row_tint)
            self.table.setItem(row, 8, ns_day_item)

            # Submit Time
            if job.submission_time:
                submit_time = job.submission_time.strftime("%Y-%m-%d %H:%M")
            else:
                submit_time = "-"
            submit_item = QTableWidgetItem(submit_time)
            submit_item.setForeground(_DEFAULT_FG)
            if row_tint:
                submit_item.setBackground(row_tint)
            self.table.setItem(row, 9, submit_item)

        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)

    @staticmethod
    def _parse_time_to_seconds(time_str: str) -> int:
        """
        Parse SLURM time format to seconds.

        Supports: D-HH:MM:SS, HH:MM:SS, H:MM:SS, MM:SS, UNLIMITED

        Args:
            time_str: Time string in SLURM format

        Returns:
            Total seconds
        """
        if not time_str or time_str == "UNLIMITED":
            return 0
        try:
            days = 0
            if '-' in time_str:
                day_part, time_str = time_str.split('-', 1)
                days = int(day_part)
            parts = time_str.split(':')
            if len(parts) == 3:
                return days * 86400 + int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:
                return days * 86400 + int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 1:
                return days * 86400 + int(parts[0])
        except (ValueError, IndexError):
            pass
        return 0

    def _calculate_progress(self, job: JobInfo) -> int:
        """Calculate job progress as elapsed / time_limit percentage."""
        state = job.state.upper() if job.state else ""

        if state == "COMPLETED":
            return 100
        if state in ("FAILED", "CANCELLED", "TIMEOUT"):
            return 0
        if state != "RUNNING":
            return 0

        limit_secs = self._parse_time_to_seconds(job.time_limit) if job.time_limit else 0
        if limit_secs <= 0:
            return 0

        # Try elapsed string first, fall back to start_time → now
        elapsed_secs = self._parse_time_to_seconds(job.elapsed) if job.elapsed else 0
        if elapsed_secs <= 0 and job.start_time:
            from datetime import datetime
            elapsed_secs = int((datetime.now() - job.start_time).total_seconds())

        return min(100, int(elapsed_secs * 100 / limit_secs)) if elapsed_secs > 0 else 0

    def _update_count_label(self):
        """Update the job count label."""
        total = len(self.jobs)
        shown = len(self.filtered_jobs)
        self.job_count_label.setText(f"Showing {shown} of {total} jobs")

    def _on_job_selected(self):
        """Handle job selection — emit for the last selected row."""
        selected_items = self.table.selectedItems()
        if selected_items:
            row = selected_items[0].row()
            if 0 <= row < len(self.filtered_jobs):
                job = self.filtered_jobs[row]
                self.job_selected.emit(job)

    def _on_job_double_clicked(self, item: QTableWidgetItem):
        """Handle job double-click."""
        row = item.row()
        if 0 <= row < len(self.filtered_jobs):
            job = self.filtered_jobs[row]
            self.job_double_clicked.emit(job)

    def _on_refresh_clicked(self):
        """Handle refresh button click (placeholder for parent)."""
        pass

    # Signals for context-menu actions that the parent (JobManagerTab) handles
    cancel_requested = pyqtSignal(object)  # JobInfo

    def _create_context_menu(self, position):
        """
        Show right-click context menu.

        Args:
            position: Position of right-click
        """
        item = self.table.itemAt(position)
        if not item:
            return

        row = item.row()
        if row < 0 or row >= len(self.filtered_jobs):
            return

        job = self.filtered_jobs[row]

        menu = QMenu()

        cancel_action = menu.addAction("Cancel Job")
        resubmit_action = menu.addAction("Resubmit Job")
        menu.addSeparator()
        copy_id_action = menu.addAction("Copy Job ID")
        copy_name_action = menu.addAction("Copy Job Name")

        # Disable certain actions based on job state
        if job.state.upper() not in ("RUNNING", "PENDING"):
            cancel_action.setEnabled(False)

        action = menu.exec_(self.table.mapToGlobal(position))

        if action == cancel_action:
            self.cancel_requested.emit(job)
        elif action == resubmit_action:
            self.resubmit_requested.emit(job)
        elif action == copy_id_action:
            QApplication.clipboard().setText(job.job_id)
        elif action == copy_name_action:
            QApplication.clipboard().setText(job.name)

    def _confirm_action(self, message: str) -> bool:
        """
        Show confirmation dialog.

        Args:
            message: Message to display

        Returns:
            True if user confirmed, False otherwise
        """
        reply = QMessageBox.question(
            self, "Confirm Action", message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        return reply == QMessageBox.Yes

    def get_selected_job(self) -> Optional[JobInfo]:
        """
        Get the currently selected job (first selected row).

        Returns:
            JobInfo object or None if no job selected
        """
        selected_items = self.table.selectedItems()
        if selected_items:
            row = selected_items[0].row()
            if 0 <= row < len(self.filtered_jobs):
                return self.filtered_jobs[row]
        return None

    def get_selected_jobs(self) -> List[JobInfo]:
        """
        Get all selected jobs (for multi-select).

        Returns:
            List of selected JobInfo objects
        """
        selected_rows = set()
        for item in self.table.selectedItems():
            selected_rows.add(item.row())

        jobs = []
        for row in sorted(selected_rows):
            if 0 <= row < len(self.filtered_jobs):
                jobs.append(self.filtered_jobs[row])
        return jobs
