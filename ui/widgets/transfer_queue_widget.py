"""Transfer queue panel — shows every active and completed transfer with
progress bars, speed, ETA, and pause/cancel controls."""

import logging
from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QProgressBar, QAbstractItemView
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt5.QtGui import QIcon, QColor, QFont, QPixmap

logger = logging.getLogger(__name__)


@dataclass
class TransferTask:
    """Data class representing a file transfer task."""
    task_id: str
    filename: str
    source_path: str
    destination_path: str
    is_upload: bool  # True for upload, False for download
    total_bytes: int = 0
    bytes_transferred: int = 0
    status: str = "pending"  # pending, in_progress, completed, failed, cancelled
    speed_bps: float = 0.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_message: str = ""


class TransferItemWidget(QWidget):
    """A single transfer row with progress bar, speed, ETA, and action buttons."""

    pause_requested = pyqtSignal(str)  # transfer_id
    cancel_requested = pyqtSignal(str)  # transfer_id

    def __init__(self, transfer: TransferTask, parent=None):
        super().__init__(parent)
        self.transfer = transfer
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            TransferItemWidget {
                background: rgba(30, 32, 48, 0.6);
                border-radius: 8px;
            }
        """)

        layout = QHBoxLayout()
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # Icon (upload/download arrow)
        icon_label = QLabel()
        if self.transfer.is_upload:
            icon_label.setText("↑")
            icon_label.setStyleSheet("""
                font-size: 14px; font-weight: bold;
                color: rgba(14, 165, 233, 0.9);
                background: rgba(14, 165, 233, 0.12);
                border-radius: 12px;
                padding: 4px;
                min-width: 24px; min-height: 24px;
                qproperty-alignment: AlignCenter;
            """)
        else:
            icon_label.setText("↓")
            icon_label.setStyleSheet("""
                font-size: 14px; font-weight: bold;
                color: rgba(166, 218, 149, 0.9);
                background: rgba(166, 218, 149, 0.12);
                border-radius: 12px;
                padding: 4px;
                min-width: 24px; min-height: 24px;
                qproperty-alignment: AlignCenter;
            """)
        icon_label.setFixedSize(28, 28)
        layout.addWidget(icon_label)

        # File info column
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)

        # Filename
        filename_label = QLabel(self.transfer.filename)
        filename_label.setStyleSheet("""
            color: #cad3f5;
            font-size: 12px;
            font-weight: 600;
        """)
        filename_label.setMaximumWidth(300)
        info_layout.addWidget(filename_label)

        # Source → Destination path
        path_text = f"{os.path.basename(self.transfer.source_path)} → {os.path.basename(self.transfer.destination_path)}"
        path_label = QLabel(path_text)
        path_label.setStyleSheet("color: rgba(202,211,245,0.35); font-size: 10px;")
        path_label.setMaximumWidth(300)
        path_label.setToolTip(f"{self.transfer.source_path} → {self.transfer.destination_path}")
        info_layout.addWidget(path_label)

        layout.addLayout(info_layout, 1)

        # Progress bar (range 0-1000 for 0.1% resolution on large files)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background: rgba(255,255,255,0.06);
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(14, 165, 233, 0.8), stop:1 rgba(125, 196, 228, 0.8));
                border-radius: 3px;
            }
        """)
        self._update_progress()
        layout.addWidget(self.progress_bar)

        # Speed label
        self.speed_label = QLabel("—")
        self.speed_label.setMaximumWidth(80)
        self.speed_label.setAlignment(Qt.AlignRight)
        self.speed_label.setStyleSheet("color: rgba(202,211,245,0.4); font-size: 10px;")
        layout.addWidget(self.speed_label)

        # ETA label
        self.eta_label = QLabel("—")
        self.eta_label.setMaximumWidth(80)
        self.eta_label.setAlignment(Qt.AlignRight)
        self.eta_label.setStyleSheet("color: rgba(202,211,245,0.4); font-size: 10px;")
        layout.addWidget(self.eta_label)

        # Shared button style
        btn_qss = """
            QPushButton {
                background: rgba(202,211,245,0.06);
                border: 1px solid rgba(202,211,245,0.08);
                border-radius: 6px;
                color: rgba(202,211,245,0.6);
                font-size: 12px;
                padding: 2px;
            }
            QPushButton:hover {
                background: rgba(202,211,245,0.12);
                color: rgba(202,211,245,0.85);
            }
        """

        # Pause/Resume button
        self.pause_button = QPushButton("⏸")
        self.pause_button.setFixedSize(28, 28)
        self.pause_button.setToolTip("Pause transfer")
        self.pause_button.setStyleSheet(btn_qss)
        self.pause_button.clicked.connect(self._on_pause_clicked)
        layout.addWidget(self.pause_button)

        # Cancel button
        self.cancel_button = QPushButton("✕")
        self.cancel_button.setFixedSize(28, 28)
        self.cancel_button.setToolTip("Cancel transfer")
        self.cancel_button.setStyleSheet(btn_qss.replace(
            "rgba(202,211,245,0.6)", "rgba(237, 135, 150, 0.7)"
        ))
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        layout.addWidget(self.cancel_button)

        # Status icon
        self.status_icon = QLabel()
        self.status_icon.setFixedSize(24, 24)
        self._update_status_icon()
        layout.addWidget(self.status_icon)

        self.setLayout(layout)

    def update_progress(self, bytes_done: int, bytes_total: int):
        self.transfer.bytes_transferred = bytes_done
        self.transfer.total_bytes = bytes_total
        self._update_progress()

    def update_speed(self, speed_bps: float):
        self.transfer.speed_bps = speed_bps
        self._update_speed_label()
        self._update_eta_label()

    def set_status(self, status: str):
        self.transfer.status = status
        self._update_status_icon()

        # Update button states based on status
        if status in ["completed", "failed", "cancelled"]:
            self.pause_button.setEnabled(False)
        elif status == "in_progress":
            self.pause_button.setEnabled(True)

    def _update_progress(self):
        """Refresh the progress bar (uses 0–1000 scale for sub-percent precision)."""
        if self.transfer.total_bytes > 0:
            per_mille = int((self.transfer.bytes_transferred / self.transfer.total_bytes) * 1000)
            self.progress_bar.setValue(per_mille)
            pct_display = per_mille / 10.0
            self.progress_bar.setToolTip(
                f"{self._format_size(self.transfer.bytes_transferred)} / "
                f"{self._format_size(self.transfer.total_bytes)} "
                f"({pct_display:.1f}%)"
            )
        else:
            self.progress_bar.setValue(0)

    def _update_speed_label(self):
        """Update speed display."""
        if self.transfer.speed_bps > 0:
            speed_str = self._format_speed(self.transfer.speed_bps)
            self.speed_label.setText(speed_str)
        else:
            self.speed_label.setText("—")

    def _update_eta_label(self):
        """Update ETA display."""
        if (self.transfer.speed_bps > 0 and
                self.transfer.bytes_transferred < self.transfer.total_bytes):
            remaining_bytes = (self.transfer.total_bytes -
                             self.transfer.bytes_transferred)
            seconds_remaining = remaining_bytes / self.transfer.speed_bps
            eta_str = self._format_time(seconds_remaining)
            self.eta_label.setText(eta_str)
        else:
            self.eta_label.setText("—")

    def _update_status_icon(self):
        """Update status icon."""
        status = self.transfer.status
        base = "font-size: 13px; qproperty-alignment: AlignCenter;"
        if status == "completed":
            self.status_icon.setText("✓")
            self.status_icon.setStyleSheet(f"color: rgba(166, 218, 149, 0.9); {base}")
        elif status == "failed":
            self.status_icon.setText("✕")
            self.status_icon.setStyleSheet(f"color: rgba(237, 135, 150, 0.9); {base}")
        elif status == "cancelled":
            self.status_icon.setText("◯")
            self.status_icon.setStyleSheet(f"color: rgba(202,211,245,0.3); {base}")
        elif status == "in_progress":
            self.status_icon.setText("●")
            self.status_icon.setStyleSheet(f"color: rgba(14, 165, 233, 0.9); {base}")
        else:  # pending
            self.status_icon.setText("○")
            self.status_icon.setStyleSheet(f"color: rgba(202,211,245,0.3); {base}")

    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to human-readable size."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"

    def _format_speed(self, bps: float) -> str:
        """Format bytes per second to human-readable speed."""
        for unit in ['B/s', 'KB/s', 'MB/s', 'GB/s']:
            if bps < 1024:
                return f"{bps:.1f} {unit}"
            bps /= 1024
        return f"{bps:.1f} TB/s"

    def _format_time(self, seconds: float) -> str:
        """Format seconds to human-readable time."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}h {minutes}m"

    def _on_pause_clicked(self):
        """Handle pause button click."""
        self.pause_requested.emit(self.transfer.task_id)

    def _on_cancel_clicked(self):
        """Handle cancel button click."""
        self.cancel_requested.emit(self.transfer.task_id)


class TransferQueueWidget(QWidget):
    """Full transfer queue widget with per-item controls and aggregate stats."""

    pause_requested = pyqtSignal(str)  # transfer_id
    cancel_requested = pyqtSignal(str)  # transfer_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.transfers: Dict[str, TransferTask] = {}
        self.transfer_widgets: Dict[str, TransferItemWidget] = {}
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            TransferQueueWidget {
                background: rgba(26, 27, 38, 0.95);
                border-top: 1px solid #363a4f;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        # HEADER SECTION
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        header_label = QLabel("Transfers")
        header_label.setStyleSheet("""
            color: rgba(202,211,245,0.6);
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.5px;
        """)
        header_layout.addWidget(header_label)

        header_layout.addStretch()

        queue_btn_qss = """
            QPushButton {
                background: rgba(202,211,245,0.06);
                border: 1px solid rgba(202,211,245,0.08);
                border-radius: 6px;
                color: rgba(202,211,245,0.6);
                padding: 4px 12px;
                font-size: 10px;
            }
            QPushButton:hover {
                background: rgba(202,211,245,0.1);
                color: rgba(202,211,245,0.85);
            }
        """

        # Clear completed button
        clear_button = QPushButton("Clear Completed")
        clear_button.setMaximumWidth(150)
        clear_button.setStyleSheet(queue_btn_qss)
        clear_button.clicked.connect(self.clear_completed)
        clear_button.setToolTip("Remove completed transfers from queue")
        header_layout.addWidget(clear_button)

        # Cancel all button
        cancel_all_button = QPushButton("Cancel All")
        cancel_all_button.setMaximumWidth(100)
        cancel_all_button.setStyleSheet(queue_btn_qss.replace(
            "rgba(202,211,245,0.6)", "rgba(237, 135, 150, 0.6)"
        ))
        cancel_all_button.clicked.connect(self._on_cancel_all)
        cancel_all_button.setToolTip("Cancel all pending and in-progress transfers")
        header_layout.addWidget(cancel_all_button)

        layout.addLayout(header_layout)

        # TRANSFER LIST
        self.transfer_list = QListWidget()
        self.transfer_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.transfer_list.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                background: transparent;
                border: none;
                padding: 2px 0;
            }
        """)
        layout.addWidget(self.transfer_list)

        # STATISTICS SECTION
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("color: rgba(202,211,245,0.35); font-size: 10px;")
        self._update_statistics()
        layout.addWidget(self.stats_label)

        self.setLayout(layout)

    def add_transfer(self, transfer: TransferTask):
        """Add a new transfer to the queue."""
        try:
            self.transfers[transfer.task_id] = transfer

            # Create widget
            widget = TransferItemWidget(transfer)
            widget.pause_requested.connect(self._on_pause_requested)
            widget.cancel_requested.connect(self._on_cancel_requested)
            self.transfer_widgets[transfer.task_id] = widget

            # Add to list
            item = QListWidgetItem()
            item.setSizeHint(QSize(600, 90))
            self.transfer_list.addItem(item)
            self.transfer_list.setItemWidget(item, widget)

            # Debounce statistics update — avoid recalculating on every add
            # when many transfers are queued in rapid succession
            if not hasattr(self, '_stats_timer'):
                from PyQt5.QtCore import QTimer
                self._stats_timer = QTimer(self)
                self._stats_timer.setSingleShot(True)
                self._stats_timer.setInterval(50)
                self._stats_timer.timeout.connect(self._update_statistics)
            self._stats_timer.start()

            logger.info(f"Added transfer: {transfer.task_id}")

        except Exception as e:
            logger.error(f"Failed to add transfer: {e}")

    def update_progress(self, transfer_id: str, bytes_done: int, bytes_total: int):
        """Update progress for a transfer."""
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            transfer.bytes_transferred = bytes_done
            transfer.total_bytes = bytes_total

            if transfer_id in self.transfer_widgets:
                widget = self.transfer_widgets[transfer_id]
                widget.update_progress(bytes_done, bytes_total)

            self._update_statistics()

    def update_speed(self, transfer_id: str, speed_bps: float):
        """Update speed for a transfer."""
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            transfer.speed_bps = speed_bps

            if transfer_id in self.transfer_widgets:
                widget = self.transfer_widgets[transfer_id]
                widget.update_speed(speed_bps)

    def mark_completed(self, transfer_id: str, success: bool):
        """Mark a transfer as completed or failed."""
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            transfer.status = "completed" if success else "failed"
            transfer.end_time = datetime.now()

            if transfer_id in self.transfer_widgets:
                widget = self.transfer_widgets[transfer_id]
                widget.set_status(transfer.status)

            self._update_statistics()
            logger.info(f"Transfer {transfer_id} {'completed' if success else 'failed'}")

    def pause_transfer(self, transfer_id: str):
        """Pause a transfer."""
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            if transfer.status == "in_progress":
                transfer.status = "paused"

                if transfer_id in self.transfer_widgets:
                    widget = self.transfer_widgets[transfer_id]
                    widget.set_status("paused")

                self._update_statistics()

    def resume_transfer(self, transfer_id: str):
        """Resume a paused transfer."""
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            if transfer.status == "paused":
                transfer.status = "in_progress"

                if transfer_id in self.transfer_widgets:
                    widget = self.transfer_widgets[transfer_id]
                    widget.set_status("in_progress")

                self._update_statistics()

    def cancel_transfer(self, transfer_id: str):
        """Cancel a transfer."""
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            transfer.status = "cancelled"

            if transfer_id in self.transfer_widgets:
                widget = self.transfer_widgets[transfer_id]
                widget.set_status("cancelled")

            self._update_statistics()

    def clear_completed(self):
        """Remove completed transfers from queue."""
        completed_ids = [
            task_id for task_id, transfer in self.transfers.items()
            if transfer.status in ["completed", "failed", "cancelled"]
        ]

        for task_id in completed_ids:
            if task_id in self.transfer_widgets:
                # Find and remove the item
                w = self.transfer_widgets[task_id]
                for i in range(self.transfer_list.count()):
                    item = self.transfer_list.item(i)
                    widget = self.transfer_list.itemWidget(item)
                    if widget is w:
                        self.transfer_list.takeItem(i)
                        break
                w.deleteLater()
                del self.transfer_widgets[task_id]
            del self.transfers[task_id]

        self._update_statistics()

    def _update_statistics(self):
        """Update statistics label."""
        if not self.transfers:
            self.stats_label.setText("No transfers")
            return

        completed = sum(1 for t in self.transfers.values()
                       if t.status == "completed")
        in_progress = sum(1 for t in self.transfers.values()
                         if t.status == "in_progress")
        total = len(self.transfers)

        total_bytes_transferred = sum(t.bytes_transferred
                                     for t in self.transfers.values())
        total_bytes = sum(t.total_bytes for t in self.transfers.values())

        total_transferred_str = self._format_size(total_bytes_transferred)
        total_str = self._format_size(total_bytes)

        self.stats_label.setText(
            f"{in_progress} active • {completed}/{total} completed • "
            f"{total_transferred_str} / {total_str}"
        )

    def _on_pause_requested(self, transfer_id: str):
        """Handle pause request from item widget."""
        self.pause_requested.emit(transfer_id)

    def _on_cancel_requested(self, transfer_id: str):
        """Handle cancel request from item widget."""
        self.cancel_requested.emit(transfer_id)

    def _on_cancel_all(self):
        """Cancel all active transfers."""
        for transfer_id, transfer in list(self.transfers.items()):
            if transfer.status in ["pending", "in_progress", "paused"]:
                self.cancel_transfer(transfer_id)
                self.cancel_requested.emit(transfer_id)

    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to human-readable size."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"
