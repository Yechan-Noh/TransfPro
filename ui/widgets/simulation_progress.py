"""
Simulation progress monitor widget for TransfPro dashboard.

This module provides widgets for displaying per-simulation progress information
including progress bars, performance metrics, and timing information.
"""

import logging
from typing import List, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame,
    QLabel, QProgressBar, QPushButton
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from transfpro.models.job import SimulationProgress

logger = logging.getLogger(__name__)


class SimulationProgressWidget(QWidget):
    """
    Shows progress bars and stats for each running GROMACS simulation.

    Provides a scrollable area containing individual simulation progress rows
    with monitoring of active GROMACS jobs and their progress metrics.

    Signals:
        view_job_requested: Emitted with job_id when user clicks "View" button
        view_log_requested: Emitted with (job_id, log_path) when log viewing is requested
    """

    view_job_requested = pyqtSignal(str)  # job_id
    view_log_requested = pyqtSignal(str, str)  # job_id, log_path

    def __init__(self, parent=None):
        """
        Initialize the simulation progress widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.simulation_rows: dict = {}  # job_id -> SimulationRow
        self._setup_ui()

    def _setup_ui(self):
        """Set up the simulation progress widget layout."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title
        title = QLabel("Active Simulations")
        title.setFont(QFont("Arial", 11, QFont.Bold))
        title.setStyleSheet("color: #E0E0E0;")
        title.setMargin(12)
        layout.addWidget(title)

        # Create scroll area for simulation rows
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                width: 10px;
                background-color: #2b2b2b;
            }
            QScrollBar::handle:vertical {
                background-color: #555555;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #777777;
            }
        """)

        # Container widget for scroll area
        container = QWidget()
        container.setStyleSheet("background-color: transparent;")
        self.container_layout = QVBoxLayout()
        self.container_layout.setContentsMargins(8, 8, 8, 8)
        self.container_layout.setSpacing(8)
        container.setLayout(self.container_layout)

        # Add empty state label
        self.empty_label = QLabel("No running simulations")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color: #888888; padding: 32px;")
        self.empty_label.setFont(QFont("Arial", 10))
        self.container_layout.addWidget(self.empty_label)

        scroll_area.setWidget(container)
        layout.addWidget(scroll_area)

        self.setLayout(layout)

    def update_simulations(self, simulations: List[SimulationProgress]):
        """
        Update or create progress rows for active simulations.

        Removes rows for jobs no longer running, adds rows for new jobs,
        and updates existing rows with current progress data.

        Args:
            simulations: List of SimulationProgress objects for active jobs
        """
        if not simulations:
            # Show empty state
            self.empty_label.show()
            # Clear all rows
            for job_id in list(self.simulation_rows.keys()):
                self._remove_row(job_id)
            return

        # Hide empty label
        self.empty_label.hide()

        # Get current job IDs
        current_job_ids = {sim.job_id for sim in simulations}
        existing_job_ids = set(self.simulation_rows.keys())

        # Remove rows for completed/failed jobs
        for job_id in existing_job_ids - current_job_ids:
            self._remove_row(job_id)

        # Add or update rows
        for sim in simulations:
            if sim.job_id in self.simulation_rows:
                # Update existing row
                row = self.simulation_rows[sim.job_id]
                row.update_progress(
                    percent=sim.percent_complete,
                    current_time_ps=sim.current_time_ps,
                    total_time_ps=sim.total_time_ps,
                    ns_per_day=sim.ns_per_day,
                    wall_time=sim.wall_time_used,
                    eta_hours=sim.estimated_hours_remaining
                )
            else:
                # Create new row
                row = SimulationRow(sim.job_id, sim.job_name, parent=self)
                row.view_job_clicked.connect(self.view_job_requested.emit)
                row.view_log_clicked.connect(self.view_log_requested.emit)
                row.update_progress(
                    percent=sim.percent_complete,
                    current_time_ps=sim.current_time_ps,
                    total_time_ps=sim.total_time_ps,
                    ns_per_day=sim.ns_per_day,
                    wall_time=sim.wall_time_used,
                    eta_hours=sim.estimated_hours_remaining
                )
                self.simulation_rows[sim.job_id] = row
                self.container_layout.insertWidget(
                    self.container_layout.count() - 1, row
                )

    def _remove_row(self, job_id: str):
        """
        Remove a simulation progress row.

        Args:
            job_id: Job ID to remove
        """
        if job_id in self.simulation_rows:
            row = self.simulation_rows[job_id]
            self.container_layout.removeWidget(row)
            row.deleteLater()
            del self.simulation_rows[job_id]

    def clear_all(self):
        """Clear all simulation rows."""
        for job_id in list(self.simulation_rows.keys()):
            self._remove_row(job_id)
        self.empty_label.show()


class SimulationRow(QFrame):
    """
    Single simulation progress row.

    Displays progress information for a single GROMACS simulation including
    progress bar, performance metrics, and timing information.

    Signals:
        view_job_clicked: Emitted with job_id when "View Job" button is clicked
        view_log_clicked: Emitted with (job_id, log_path) when log viewing is requested
    """

    view_job_clicked = pyqtSignal(str)
    view_log_clicked = pyqtSignal(str, str)

    def __init__(self, job_id: str, job_name: str, parent=None):
        """
        Initialize a simulation progress row.

        Args:
            job_id: Job identifier
            job_name: Human-readable job name
            parent: Parent widget
        """
        super().__init__(parent)
        self.job_id = job_id
        self.job_name = job_name
        self.log_file = ""

        # Set frame properties
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Plain)
        self.setLineWidth(1)
        self.setFixedHeight(50)

        # Apply styling
        self.setStyleSheet("""
            QFrame {
                background-color: #383838;
                border: 1px solid #4d4d4d;
                border-radius: 4px;
                padding: 8px;
            }
        """)

        # Create layout
        self._setup_ui()

    def _setup_ui(self):
        """Set up the simulation row layout."""
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(8, 4, 8, 4)
        main_layout.setSpacing(12)

        # Job name label (fixed width 200px)
        self.name_label = QLabel(self.job_name[:40])
        self.name_label.setFont(QFont("Arial", 10, QFont.Bold))
        self.name_label.setStyleSheet("color: #E0E0E0;")
        self.name_label.setFixedWidth(200)
        self.name_label.setToolTip(self.job_name)
        main_layout.addWidget(self.name_label)

        # Progress bar with percentage text
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #555555;
                border-radius: 4px;
                background-color: #1a1b26;
                color: #cad3f5;
                text-align: center;
                font-size: 8px;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #0ea5e9;
                border-radius: 3px;
            }
        """)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        main_layout.addWidget(self.progress_bar, 1)

        # ns/day label (fixed width 80px)
        self.ns_per_day_label = QLabel("0.0 ns/day")
        self.ns_per_day_label.setFont(QFont("Arial", 8))
        self.ns_per_day_label.setStyleSheet("color: #7dc4e4;")
        self.ns_per_day_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.ns_per_day_label.setFixedWidth(80)
        main_layout.addWidget(self.ns_per_day_label)

        # Wall time label (fixed width 80px)
        self.wall_time_label = QLabel("0h")
        self.wall_time_label.setFont(QFont("Arial", 8))
        self.wall_time_label.setStyleSheet("color: #eed49f;")
        self.wall_time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.wall_time_label.setFixedWidth(80)
        main_layout.addWidget(self.wall_time_label)

        # ETA label (fixed width 100px)
        self.eta_label = QLabel("ETA: --")
        self.eta_label.setFont(QFont("Arial", 8))
        self.eta_label.setStyleSheet("color: #a6da95;")
        self.eta_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.eta_label.setFixedWidth(100)
        main_layout.addWidget(self.eta_label)

        # View button
        self.view_button = QPushButton("View")
        self.view_button.setFixedSize(50, 30)
        self.view_button.setFont(QFont("Arial", 8))
        self.view_button.setStyleSheet("""
            QPushButton {
                background-color: #0ea5e9;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0284c7;
            }
            QPushButton:pressed {
                background-color: #0369a1;
            }
        """)
        self.view_button.clicked.connect(lambda: self.view_job_clicked.emit(self.job_id))
        main_layout.addWidget(self.view_button)

        self.setLayout(main_layout)

    def update_progress(self, percent: float, current_time_ps: float,
                       total_time_ps: float, ns_per_day: float,
                       wall_time: str, eta_hours: float):
        """
        Update the simulation progress row with new data.

        Args:
            percent: Completion percentage (0-100)
            current_time_ps: Current simulation time in picoseconds
            total_time_ps: Total simulation time in picoseconds
            ns_per_day: Performance metric (nanoseconds per day)
            wall_time: Wall clock time used (HH:MM:SS format)
            eta_hours: Estimated hours remaining
        """
        # Update progress bar
        percent_int = int(max(0, min(100, percent)))
        self.progress_bar.setValue(percent_int)
        self.progress_bar.setFormat(f"{percent_int}% | {current_time_ps:.1f}/{total_time_ps:.1f} ps")

        # Update ns/day
        self.ns_per_day_label.setText(f"{ns_per_day:.2f} ns/dy")

        # Update wall time
        self.wall_time_label.setText(wall_time)

        # Update ETA
        if eta_hours > 0:
            if eta_hours >= 24:
                days = int(eta_hours / 24)
                hours = int(eta_hours % 24)
                self.eta_label.setText(f"ETA: {days}d {hours}h")
            else:
                hours = int(eta_hours)
                mins = int((eta_hours % 1) * 60)
                self.eta_label.setText(f"ETA: {hours}h {mins}m")
        else:
            self.eta_label.setText("ETA: --")

        # Update color coding based on performance
        if ns_per_day < 1:
            color = "#F44336"  # Red for poor performance
        elif ns_per_day < 5:
            color = "#FF9800"  # Orange for moderate
        else:
            color = "#4CAF50"  # Green for good

        self.ns_per_day_label.setStyleSheet(f"color: {color};")

    def set_log_file(self, log_path: str):
        """
        Set the log file path for this simulation.

        Args:
            log_path: Path to the log file
        """
        self.log_file = log_path
