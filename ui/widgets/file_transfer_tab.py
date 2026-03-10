"""Dual-pane file browser with drag-and-drop transfers and a floating
progress overlay. This is the main UI for uploading/downloading files."""

import logging
import uuid
import os
import subprocess
import sys
import tempfile
from typing import List, Dict
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSplitter,
    QMessageBox, QProgressBar, QLabel
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QTimer, QSize
from PyQt5.QtGui import QIcon, QColor

from transfpro.config.constants import MAX_CONCURRENT_TRANSFERS
try:
    from transfpro.core.gromacs_parser import (
        GROMACS_INPUT_EXTENSIONS, GROMACS_OUTPUT_EXTENSIONS,
    )
except ImportError:
    GROMACS_INPUT_EXTENSIONS = set()
    GROMACS_OUTPUT_EXTENSIONS = set()
from transfpro.models.transfer import (
    TransferTask as ModelTransferTask,
    TransferDirection, TransferStatus
)
from transfpro.workers.transfer_worker import TransferWorker
from transfpro.workers.base_worker import BaseWorker
from transfpro.ui.widgets.file_browser_pane import FileBrowserPane
from transfpro.ui.widgets.mini_terminal import MiniTerminal
from transfpro.ui.widgets.transfer_queue_widget import (
    TransferQueueWidget, TransferTask
)
from transfpro.ui.dialogs.transfer_confirm_dialog import TransferConfirmDialog

logger = logging.getLogger(__name__)


class _TransferRowWidget(QWidget):
    """One row in the floating overlay — shows a single file's transfer progress."""

    cancel_requested = pyqtSignal(str)  # transfer_id

    _UPLOAD_ICON_QSS = (
        "color: rgba(14,165,233,0.9); font-size: 11px; font-weight: bold;"
        "background: rgba(14,165,233,0.12); border-radius: 8px;"
        "qproperty-alignment: AlignCenter;"
    )
    _DOWNLOAD_ICON_QSS = (
        "color: rgba(166,218,149,0.9); font-size: 11px; font-weight: bold;"
        "background: rgba(166,218,149,0.12); border-radius: 8px;"
        "qproperty-alignment: AlignCenter;"
    )
    _DONE_ICON_QSS = (
        "color: rgba(166,218,149,0.9); font-size: 11px; font-weight: bold;"
        "background: rgba(166,218,149,0.18); border-radius: 8px;"
        "qproperty-alignment: AlignCenter;"
    )
    _FAIL_ICON_QSS = (
        "color: rgba(237,135,150,0.9); font-size: 11px; font-weight: bold;"
        "background: rgba(237,135,150,0.18); border-radius: 8px;"
        "qproperty-alignment: AlignCenter;"
    )
    _CANCEL_ICON_QSS = (
        "color: rgba(245,169,127,0.9); font-size: 11px; font-weight: bold;"
        "background: rgba(245,169,127,0.18); border-radius: 8px;"
        "qproperty-alignment: AlignCenter;"
    )

    def __init__(self, task_id: str, filename: str, is_upload: bool, parent=None):
        super().__init__(parent)
        self.task_id = task_id
        self.is_upload = is_upload
        self.setFixedHeight(36)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(2)

        # Top: icon + filename + speed + cancel
        top = QHBoxLayout()
        top.setSpacing(4)

        self.icon_label = QLabel("↑" if is_upload else "↓")
        self.icon_label.setFixedSize(16, 16)
        self.icon_label.setStyleSheet(
            self._UPLOAD_ICON_QSS if is_upload else self._DOWNLOAD_ICON_QSS
        )
        top.addWidget(self.icon_label)

        self.filename_label = QLabel(filename)
        self.filename_label.setStyleSheet(
            "color: #cad3f5; font-size: 10px; font-weight: 500;"
        )
        self.filename_label.setMaximumWidth(180)
        top.addWidget(self.filename_label, 1)

        self.speed_label = QLabel("")
        self.speed_label.setStyleSheet(
            "color: rgba(202,211,245,0.4); font-size: 9px;"
        )
        self.speed_label.setFixedWidth(60)
        self.speed_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self.speed_label)

        self.pct_label = QLabel("0%")
        self.pct_label.setFixedWidth(32)
        self.pct_label.setStyleSheet(
            "color: rgba(202,211,245,0.5); font-size: 9px;"
        )
        self.pct_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self.pct_label)

        self.cancel_btn = QPushButton("✕")
        self.cancel_btn.setFixedSize(16, 16)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background: transparent; border: none;
                color: rgba(202,211,245,0.3); font-size: 9px;
            }
            QPushButton:hover {
                color: rgba(237, 135, 150, 0.9);
            }
        """)
        self.cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self.task_id))
        top.addWidget(self.cancel_btn)

        layout.addLayout(top)

        # Bottom: thin progress bar (range 0-1000 for 0.1% resolution)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setTextVisible(False)
        bar_color = "rgba(14, 165, 233, 0.8)" if is_upload else "rgba(166, 218, 149, 0.8)"
        bar_end = "rgba(125, 196, 228, 0.8)" if is_upload else "rgba(200, 235, 190, 0.8)"
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: rgba(255,255,255,0.06);
                border: none; border-radius: 1px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {bar_color}, stop:1 {bar_end});
                border-radius: 1px;
            }}
        """)
        layout.addWidget(self.progress_bar)

    def set_progress(self, pct_tenths: int):
        """Set progress in tenths of a percent (0–1000 maps to 0.0%–100.0%)."""
        self.progress_bar.setValue(pct_tenths)
        display = pct_tenths / 10.0
        if display >= 100.0:
            self.pct_label.setText("100%")
        elif display < 1.0:
            self.pct_label.setText(f"{display:.1f}%")
        else:
            self.pct_label.setText(f"{display:.0f}%")

    def set_speed(self, text: str):
        self.speed_label.setText(text)

    def mark_done(self, success: bool):
        if success:
            self.icon_label.setText("✓")
            self.icon_label.setStyleSheet(self._DONE_ICON_QSS)
            self.pct_label.setText("Done")
            self.progress_bar.setValue(1000)
        else:
            self.icon_label.setText("✕")
            self.icon_label.setStyleSheet(self._FAIL_ICON_QSS)
            self.pct_label.setText("Fail")
        self.speed_label.setText("")
        self.cancel_btn.hide()

    def mark_cancelled(self):
        self.icon_label.setText("⊘")
        self.icon_label.setStyleSheet(self._CANCEL_ICON_QSS)
        self.pct_label.setText("Cancelled")
        self.pct_label.setFixedWidth(52)
        self.speed_label.setText("")
        self.cancel_btn.hide()
        # Dim the progress bar
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background: rgba(255,255,255,0.04);
                border: none; border-radius: 1px;
            }
            QProgressBar::chunk {
                background: rgba(245, 169, 127, 0.4);
                border-radius: 1px;
            }
        """)


class FloatingTransferBox(QWidget):
    """Bottom-right overlay that tracks every active transfer at a glance."""

    cancel_requested = pyqtSignal(str)  # transfer_id
    cancel_all_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.transfers: Dict[str, TransferTask] = {}
        self._rows: Dict[str, _TransferRowWidget] = {}
        self.setFixedWidth(360)
        self.setStyleSheet("""
            FloatingTransferBox {
                background: rgba(26, 27, 38, 0.95);
                border: 1px solid rgba(14, 165, 233, 0.25);
                border-radius: 10px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(4)

        # ── Header: summary line ──
        header = QHBoxLayout()
        header.setSpacing(6)

        self.header_icon = QLabel("⇅")
        self.header_icon.setFixedSize(20, 20)
        self.header_icon.setStyleSheet(
            "color: rgba(14,165,233,0.9); font-size: 13px; font-weight: bold;"
            "background: rgba(14,165,233,0.12); border-radius: 10px;"
            "qproperty-alignment: AlignCenter;"
        )
        header.addWidget(self.header_icon)

        self.header_label = QLabel("Transfers")
        self.header_label.setStyleSheet(
            "color: #cad3f5; font-size: 11px; font-weight: 700;"
        )
        header.addWidget(self.header_label, 1)

        self.agg_speed_label = QLabel("")
        self.agg_speed_label.setStyleSheet(
            "color: rgba(14,165,233,0.6); font-size: 10px; font-weight: 600;"
        )
        header.addWidget(self.agg_speed_label)

        self.cancel_all_btn = QPushButton("Cancel All")
        self.cancel_all_btn.setFixedHeight(18)
        self.cancel_all_btn.setStyleSheet("""
            QPushButton {
                background: rgba(237, 135, 150, 0.15);
                border: 1px solid rgba(237, 135, 150, 0.3);
                border-radius: 4px; color: rgba(237, 135, 150, 0.8);
                font-size: 9px; font-weight: 600;
                padding: 0 8px;
            }
            QPushButton:hover {
                background: rgba(237, 135, 150, 0.3);
                color: rgba(237, 135, 150, 1.0);
            }
        """)
        self.cancel_all_btn.clicked.connect(self.cancel_all_requested.emit)
        header.addWidget(self.cancel_all_btn)

        main_layout.addLayout(header)

        # ── Aggregate progress bar (0-1000 for 0.1% resolution) ──
        self.agg_bar = QProgressBar()
        self.agg_bar.setRange(0, 1000)
        self.agg_bar.setFixedHeight(4)
        self.agg_bar.setTextVisible(False)
        self.agg_bar.setStyleSheet("""
            QProgressBar {
                background: rgba(255,255,255,0.06);
                border: none; border-radius: 2px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(14, 165, 233, 0.7),
                    stop:1 rgba(166, 218, 149, 0.7));
                border-radius: 2px;
            }
        """)
        main_layout.addWidget(self.agg_bar)

        # ── Separator ──
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(202,211,245,0.08);")
        main_layout.addWidget(sep)

        # ── Per-transfer rows container ──
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(1)
        main_layout.addLayout(self.rows_layout)

        self.hide()

    # ── Public API ──

    def add_transfer(self, transfer: TransferTask):
        self.transfers[transfer.task_id] = transfer

        # Create a row widget for this transfer
        row = _TransferRowWidget(
            transfer.task_id, transfer.filename, transfer.is_upload, self
        )
        row.cancel_requested.connect(self.cancel_requested.emit)
        self._rows[transfer.task_id] = row
        self.rows_layout.addWidget(row)

        # Coalesce layout recalculations — if many transfers are added in
        # rapid succession, only the last one triggers resize/reposition.
        if not hasattr(self, '_layout_timer'):
            self._layout_timer = QTimer(self)
            self._layout_timer.setSingleShot(True)
            self._layout_timer.setInterval(50)
            self._layout_timer.timeout.connect(self._deferred_layout)
        self._layout_timer.start()  # restart if already running
        self.show()

    def _deferred_layout(self):
        """Called once after a batch of add_transfer() calls finishes."""
        self._update_header()
        self._resize_to_fit()
        self._reposition()

    def update_progress(self, task_id: str, bytes_done: int, bytes_total: int):
        if task_id in self.transfers:
            t = self.transfers[task_id]
            t.bytes_transferred = bytes_done
            t.total_bytes = bytes_total

            if task_id in self._rows and t.total_bytes > 0:
                pct_tenths = int(t.bytes_transferred / t.total_bytes * 1000)
                self._rows[task_id].set_progress(pct_tenths)

            self._update_aggregate_bar()

    def update_speed(self, task_id: str, speed_bps: float):
        if task_id in self.transfers:
            self.transfers[task_id].speed_bps = speed_bps
            if task_id in self._rows:
                self._rows[task_id].set_speed(self._format_speed(speed_bps))
            self._update_header()

    def mark_completed(self, task_id: str, success: bool):
        if task_id in self.transfers:
            # Don't overwrite cancelled status with "failed" from the worker signal
            if self.transfers[task_id].status == "cancelled":
                return
            self.transfers[task_id].status = "completed" if success else "failed"
            if task_id in self._rows:
                self._rows[task_id].mark_done(success)

            self._update_header()
            self._update_aggregate_bar()

            # If all done, auto-hide after delay
            active = [t for t in self.transfers.values()
                      if t.status in ("pending", "in_progress")]
            if not active:
                QTimer.singleShot(3000, self._maybe_hide)

    def cancel_transfer(self, task_id: str):
        if task_id in self.transfers:
            self.transfers[task_id].status = "cancelled"
            if task_id in self._rows:
                self._rows[task_id].mark_cancelled()
            self._update_header()
            self._update_aggregate_bar()

    # ── Internal ──

    def _update_header(self):
        active = [t for t in self.transfers.values()
                  if t.status in ("pending", "in_progress")]
        completed = [t for t in self.transfers.values()
                     if t.status == "completed"]
        cancelled = [t for t in self.transfers.values()
                     if t.status == "cancelled"]
        total = len(self.transfers)

        # Show/hide Cancel All button based on whether there are active transfers
        self.cancel_all_btn.setVisible(len(active) > 0)

        if not active and completed:
            n = len(completed)
            self.header_label.setText(
                f"✓ {n} file{'s' if n != 1 else ''} transferred"
            )
            self.header_icon.setText("✓")
            self.header_icon.setStyleSheet(
                "color: rgba(166,218,149,0.9); font-size: 13px; font-weight: bold;"
                "background: rgba(166,218,149,0.18); border-radius: 10px;"
                "qproperty-alignment: AlignCenter;"
            )
            self.agg_speed_label.setText("")
        else:
            n_active = len(active)
            n_done = len(completed)
            if n_active > 1:
                self.header_label.setText(
                    f"{n_active} parallel transfers  ({n_done}/{total})"
                )
            elif n_active == 1:
                self.header_label.setText(
                    f"Transferring...  ({n_done}/{total})"
                    if total > 1 else "Transferring..."
                )
            else:
                self.header_label.setText("Preparing...")

            self.header_icon.setText("⇅")
            self.header_icon.setStyleSheet(
                "color: rgba(14,165,233,0.9); font-size: 13px; font-weight: bold;"
                "background: rgba(14,165,233,0.12); border-radius: 10px;"
                "qproperty-alignment: AlignCenter;"
            )

            # Aggregate speed
            total_speed = sum(t.speed_bps for t in active if t.speed_bps > 0)
            if total_speed > 0:
                self.agg_speed_label.setText(
                    f"Total: {self._format_speed(total_speed)}"
                )
            else:
                self.agg_speed_label.setText("")

    def _update_aggregate_bar(self):
        total_bytes = sum(t.total_bytes for t in self.transfers.values()
                         if t.total_bytes > 0)
        done_bytes = sum(t.bytes_transferred for t in self.transfers.values())
        if total_bytes > 0:
            self.agg_bar.setValue(int(done_bytes / total_bytes * 1000))
        else:
            self.agg_bar.setValue(0)

    def _resize_to_fit(self):
        """Dynamically resize height based on number of visible rows."""
        n = len(self._rows)
        # header ~28 + agg bar 4 + sep 1 + margins 16 + rows * 38
        h = 28 + 4 + 1 + 16 + max(n, 1) * 38
        self.setFixedHeight(min(h, 320))  # cap height

    def _maybe_hide(self):
        active = [t for t in self.transfers.values()
                  if t.status in ("pending", "in_progress")]
        if not active:
            self.cancel_all_btn.hide()
            self.hide()
            # Clean up completed rows
            for tid in list(self._rows.keys()):
                row = self._rows.pop(tid)
                self.rows_layout.removeWidget(row)
                row.deleteLater()
            self.transfers.clear()

    def _reposition(self):
        if self.parent():
            p = self.parent()
            x = p.width() - self.width() - 16
            y = p.height() - self.height() - 16
            self.move(max(0, x), max(0, y))

    @staticmethod
    def _format_speed(bps: float) -> str:
        for unit in ['B/s', 'KB/s', 'MB/s', 'GB/s']:
            if bps < 1024:
                return f"{bps:.1f} {unit}"
            bps /= 1024
        return f"{bps:.1f} TB/s"


class _DownloadStatWorker(BaseWorker):
    """Background worker that stats multiple remote paths so the UI
    thread doesn't freeze while waiting for SFTP round-trips."""

    batch_complete = pyqtSignal(list, str)  # [(remote_path, is_dir, size, filename), ...], local_dir

    def __init__(self, sftp_manager, remote_paths, local_dir):
        super().__init__()
        self._sftp_manager = sftp_manager
        self._remote_paths = remote_paths
        self._local_dir = local_dir

    def do_work(self):
        results = []
        for remote_path in self._remote_paths:
            filename = remote_path.rsplit('/', 1)[-1]
            if not filename:
                continue
            is_dir = False
            file_size = 0
            try:
                metadata = self._sftp_manager.get_file_info(remote_path)
                is_dir = metadata.is_dir if metadata else False
                file_size = metadata.size if metadata else 0
            except Exception as e:
                self.logger.debug(f"Could not stat {remote_path}: {e}")
            results.append((remote_path, is_dir, file_size, filename))
        self.batch_complete.emit(results, self._local_dir)


class FileTransferTab(QWidget):
    """The main file transfer tab — local + remote file browsers side by side
    with drag-and-drop, concurrency management, and progress tracking."""

    # Sync signals — MainWindow uses these to drive the Terminal tab
    pane_connected = pyqtSignal(str, bool, object, object)    # side, is_remote, ssh_manager, profile
    pane_disconnected = pyqtSignal(str)                        # side

    def __init__(self, database, ssh_manager=None, sftp_manager=None, parent=None):
        super().__init__(parent)
        self.database = database
        # Legacy: kept for MainWindow compatibility but panes now manage their own
        self.ssh_manager = ssh_manager
        self.sftp_manager = sftp_manager
        self.transfer_threads: Dict[str, QThread] = {}
        self.transfer_workers: Dict[str, object] = {}

        # Transfers exceeding the concurrency limit wait here
        self._pending_starts: List[tuple] = []  # [(transfer_id, direction, local, remote)]
        self._active_count = 0
        self._max_concurrent = MAX_CONCURRENT_TRANSFERS

        # Keeps the data model; UI is handled by the floating overlay instead
        self.transfer_queue = TransferQueueWidget(self)
        self.transfer_queue.hide()

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Build the split-pane layout: two file browsers + two terminals."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # MAIN CONTENT — horizontal splitter, 50/50
        self.main_splitter = QSplitter(Qt.Horizontal)

        # ── Left column: file browser + terminal ──
        self.local_vsplitter = QSplitter(Qt.Vertical)

        self.local_pane = FileBrowserPane(
            title="Left",
            database=self.database,
            parent=self
        )
        self.local_vsplitter.addWidget(self.local_pane)

        self.local_terminal = MiniTerminal(
            is_remote=False,
            parent=self
        )
        self.local_vsplitter.addWidget(self.local_terminal)

        # 5:1 ratio, adjustable by dragging the splitter handle
        self.local_vsplitter.setSizes([500, 100])
        self.local_vsplitter.setCollapsible(0, False)
        self.local_vsplitter.setCollapsible(1, False)

        self.main_splitter.addWidget(self.local_vsplitter)

        # ── Right column: file browser + terminal ──
        self.remote_vsplitter = QSplitter(Qt.Vertical)

        self.remote_pane = FileBrowserPane(
            title="Right",
            database=self.database,
            parent=self
        )
        self.remote_vsplitter.addWidget(self.remote_pane)

        self.remote_terminal = MiniTerminal(
            is_remote=False,
            parent=self
        )
        self.remote_vsplitter.addWidget(self.remote_terminal)

        # 5:1 ratio, adjustable by dragging the splitter handle
        self.remote_vsplitter.setSizes([500, 100])
        self.remote_vsplitter.setCollapsible(0, False)
        self.remote_vsplitter.setCollapsible(1, False)

        self.main_splitter.addWidget(self.remote_vsplitter)

        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        self.main_splitter.setSizes([600, 600])

        layout.addWidget(self.main_splitter, 1)

        self.setLayout(layout)

        # Floating transfer progress overlay (bottom-right)
        self.transfer_box = FloatingTransferBox(parent=self)
        self.transfer_box.cancel_requested.connect(self._on_cancel_requested)
        self.transfer_box.cancel_all_requested.connect(self._on_cancel_all_requested)

    def resizeEvent(self, event):
        """Reposition floating box on resize."""
        super().resizeEvent(event)
        if hasattr(self, 'transfer_box') and self.transfer_box.isVisible():
            self.transfer_box._reposition()

    def _connect_signals(self):
        """Wire up drag-and-drop, button clicks, and transfer queue signals."""
        # Drag-and-drop: upload goes to remote pane's SFTP, download from remote pane's SFTP
        self.local_pane.transfer_upload_requested.connect(
            lambda paths, target: self.upload_files(
                paths, target,
                sftp=self.remote_pane.sftp_manager if self.remote_pane.is_remote else self.local_pane.sftp_manager,
                refresh_pane=self.remote_pane if self.remote_pane.is_remote else self.local_pane))
        self.local_pane.transfer_download_requested.connect(
            lambda paths, target: self.download_files(
                paths, target,
                sftp=self.remote_pane.sftp_manager if self.remote_pane.is_remote else self.local_pane.sftp_manager,
                refresh_pane=self.local_pane))
        self.remote_pane.transfer_upload_requested.connect(
            lambda paths, target: self.upload_files(
                paths, target,
                sftp=self.local_pane.sftp_manager if self.local_pane.is_remote else self.remote_pane.sftp_manager,
                refresh_pane=self.local_pane if self.local_pane.is_remote else self.remote_pane))
        self.remote_pane.transfer_download_requested.connect(
            lambda paths, target: self.download_files(
                paths, target,
                sftp=self.local_pane.sftp_manager if self.local_pane.is_remote else self.remote_pane.sftp_manager,
                refresh_pane=self.remote_pane))
        # Transfer button — determine direction dynamically
        self.local_pane.transfer_button_clicked.connect(
            lambda: self._on_transfer_clicked(self.local_pane, self.remote_pane))
        self.remote_pane.transfer_button_clicked.connect(
            lambda: self._on_transfer_clicked(self.remote_pane, self.local_pane))
        # Quick Transfer Macros — each pane emits file list; lambda identifies source
        self.local_pane.transfer_macro_requested.connect(
            lambda files: self._on_transfer_macro(self.local_pane, self.remote_pane, files))
        self.remote_pane.transfer_macro_requested.connect(
            lambda files: self._on_transfer_macro(self.remote_pane, self.local_pane, files))
        self.local_pane.open_remote_file_requested.connect(self._on_open_remote_file)
        self.remote_pane.open_remote_file_requested.connect(self._on_open_remote_file)
        self.local_pane.open_remote_with_requested.connect(self._on_open_remote_with)
        self.remote_pane.open_remote_with_requested.connect(self._on_open_remote_with)
        # Keep mini-terminal cwd in sync when navigating the file browser
        self.local_pane.directory_changed.connect(self.local_terminal.cd)
        self.remote_pane.directory_changed.connect(self.remote_terminal.cd)
        self.transfer_queue.pause_requested.connect(self._on_pause_requested)
        self.transfer_queue.cancel_requested.connect(self._on_cancel_requested)
        # Pane activation — connect/disconnect mini-terminals and sync profiles
        self.local_pane.pane_activated.connect(
            lambda is_remote: self._on_pane_activated(self.local_pane, self.local_terminal, is_remote))
        self.remote_pane.pane_activated.connect(
            lambda is_remote: self._on_pane_activated(self.remote_pane, self.remote_terminal, is_remote))
        self.local_pane.pane_deactivated.connect(
            lambda: self._on_pane_deactivated(self.local_pane, self.local_terminal))
        self.remote_pane.pane_deactivated.connect(
            lambda: self._on_pane_deactivated(self.remote_pane, self.remote_terminal))
        # Profile sync: when one pane changes profiles, reload in the other
        self.local_pane.get_connection_selector().profiles_changed.connect(
            self.remote_pane.get_connection_selector().reload_profiles)
        self.remote_pane.get_connection_selector().profiles_changed.connect(
            self.local_pane.get_connection_selector().reload_profiles)

    # ── Button handlers ──

    def _on_transfer_clicked(self, source_pane, dest_pane):
        """Handle transfer button click — transfer selected files from source to dest pane."""
        selected_paths = source_pane.get_selected_paths()
        if not selected_paths:
            QMessageBox.information(self, "No Files Selected",
                                   "Please select files to transfer")
            return

        # Determine the transfer direction based on pane types
        src_remote = source_pane.is_remote
        dst_remote = dest_pane.is_remote

        if not src_remote and dst_remote:
            # Local → Cluster = upload — refresh the dest (cluster) pane
            self.upload_files(selected_paths, dest_pane.current_path,
                              sftp=dest_pane.sftp_manager,
                              refresh_pane=dest_pane)
        elif src_remote and not dst_remote:
            # Cluster → Local = download — refresh the dest (local) pane
            self.download_files(selected_paths, dest_pane.current_path,
                                sftp=source_pane.sftp_manager,
                                refresh_pane=dest_pane)
        elif not src_remote and not dst_remote:
            # Local → Local = local copy (runs in background thread)
            self._local_copy_async(selected_paths, dest_pane.current_path,
                                   dest_pane)
        elif src_remote and dst_remote:
            # Cluster → Cluster = two-hop transfer
            self._cluster_to_cluster_transfer(
                selected_paths, source_pane, dest_pane
            )

    def _local_copy_async(self, paths, dest_dir, refresh_pane=None):
        """Copy local files in a background thread to avoid freezing the UI."""
        import shutil

        def _do_copy():
            errors = []
            for p in paths:
                name = os.path.basename(p)
                dst = os.path.join(dest_dir, name)
                try:
                    if os.path.isdir(p):
                        shutil.copytree(p, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(p, dst)
                except Exception as e:
                    logger.error(f"Local copy failed: {e}")
                    errors.append((name, str(e)))
            return errors

        def _on_done(future):
            try:
                errors = future.result()
            except Exception as e:
                errors = [("(unknown)", str(e))]
            # Schedule UI updates on the main thread via QTimer
            from PyQt5.QtCore import QTimer
            def _finish():
                if errors:
                    msg = "\n".join(f"{n}: {e}" for n, e in errors)
                    QMessageBox.warning(self, "Copy Error",
                                        f"Some files failed to copy:\n{msg}")
                if refresh_pane:
                    refresh_pane.refresh()
            QTimer.singleShot(0, _finish)

        from concurrent.futures import ThreadPoolExecutor
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_do_copy)
        future.add_done_callback(_on_done)
        executor.shutdown(wait=False)

    def _cluster_to_cluster_transfer(self, remote_paths, src_pane, dst_pane):
        """Transfer files between two clusters via local temp dir.

        Downloads from source cluster to a local temp dir, then uploads
        to the destination cluster.  The upload is triggered automatically
        when all downloads complete (see _check_c2c_completion).
        """
        tmp_dir = tempfile.mkdtemp(prefix="transfpro_c2c_")
        # Track which transfer IDs belong to this c2c batch
        self._c2c_pending = {
            'tmp_dir': tmp_dir,
            'remote_paths': remote_paths,
            'dst_pane': dst_pane,
            'download_ids': set(),
            'upload_started': False,
        }

        # Download from source cluster to temp — no pane refresh needed
        self.download_files(
            remote_paths, tmp_dir,
            sftp=src_pane.sftp_manager,
            refresh_pane=None  # Don't refresh any pane for the download leg
        )

        # Collect the transfer IDs that were just enqueued
        # They're the most recent entries in the transfer_box
        for tid, t in self.transfer_box.transfers.items():
            if t.status in ("pending", "in_progress") and not t.is_upload:
                if t.destination_path.startswith(tmp_dir):
                    self._c2c_pending['download_ids'].add(tid)

    def _check_c2c_completion(self, completed_id: str):
        """Check if all c2c downloads finished and trigger the upload leg."""
        c2c = getattr(self, '_c2c_pending', None)
        if not c2c or c2c.get('upload_started'):
            return

        # Remove the completed ID from pending downloads
        c2c['download_ids'].discard(completed_id)

        # Check if all downloads are done
        if c2c['download_ids']:
            return  # Still waiting for more downloads

        # All downloads complete — upload from temp dir to dest cluster
        c2c['upload_started'] = True
        tmp_dir = c2c['tmp_dir']
        dst_pane = c2c['dst_pane']

        # Collect the files that were downloaded to tmp_dir
        local_files = []
        try:
            for entry in os.scandir(tmp_dir):
                local_files.append(entry.path)
        except Exception as e:
            logger.error(f"C2C: failed to list temp dir {tmp_dir}: {e}")
            self._c2c_pending = None
            return

        if local_files and dst_pane.sftp_manager:
            self.upload_files(
                local_files, dst_pane.current_path,
                sftp=dst_pane.sftp_manager,
                refresh_pane=dst_pane
            )

        self._c2c_pending = None

    def _on_transfer_macro(self, src_pane, dst_pane, file_names: list):
        """Execute a quick transfer macro.

        Resolves *file_names* against *src_pane*'s current directory and
        transfers them to *dst_pane*'s current directory.
        """
        import posixpath, os

        # Build full source paths
        src_dir = src_pane.current_path
        dst_dir = dst_pane.current_path

        if not src_dir or not dst_dir:
            QMessageBox.warning(self, "Macro Error",
                                "Both panes must have a current directory.")
            return

        # Need an SFTP manager for any remote side
        sftp = None
        for pane in (src_pane, dst_pane):
            if pane.is_remote and pane.sftp_manager:
                sftp = pane.sftp_manager
                break
        if not sftp:
            # Both local — use simple file copy (no SFTP needed)
            pass

        # Build full source paths (use posixpath for remote, os.path for local)
        if src_pane.is_remote:
            src_paths = [posixpath.join(src_dir, f) for f in file_names]
        else:
            src_paths = [os.path.join(src_dir, f) for f in file_names]

        # Determine transfer direction
        if src_pane.is_remote and not dst_pane.is_remote:
            # Download: remote → local
            self.download_files(src_paths, dst_dir, sftp=sftp,
                                refresh_pane=dst_pane)
        elif not src_pane.is_remote and dst_pane.is_remote:
            # Upload: local → remote
            self.upload_files(src_paths, dst_dir, sftp=sftp,
                              refresh_pane=dst_pane)
        else:
            # Both local or both remote — not a typical transfer
            QMessageBox.warning(self, "Macro Error",
                                "Macro transfer requires one local and one "
                                "remote pane.")

    # ── Pane activation handlers ──

    def _on_pane_activated(self, pane, terminal, is_remote):
        """A pane connected to Local or Cluster — set up its mini-terminal."""
        if is_remote and pane.ssh_manager:
            terminal.is_remote = True
            terminal.ssh_manager = pane.ssh_manager
            terminal.connect_terminal()
        else:
            terminal.is_remote = False
            terminal.ssh_manager = None
            terminal.connect_terminal()

        # Notify MainWindow so it can sync the Terminal tab
        side = "left" if pane is self.local_pane else "right"
        self.pane_connected.emit(
            side, is_remote,
            pane.ssh_manager,        # None for local
            pane.connected_profile,  # None for local
        )

    def _on_pane_deactivated(self, pane, terminal):
        """A pane disconnected — disconnect its mini-terminal."""
        try:
            terminal.disconnect_terminal()
        except Exception as e:
            logger.debug(f"Error disconnecting terminal: {e}")
        try:
            terminal.display.clear()
        except Exception:
            pass

        side = "left" if pane is self.local_pane else "right"
        self.pane_disconnected.emit(side)

    # ── Transfer logic ──

    def _get_sftp(self, sftp=None):
        """Return the SFTP manager to use for a transfer."""
        if sftp:
            return sftp
        # Legacy fallback: check panes for an active SFTP connection
        for pane in (self.local_pane, self.remote_pane):
            if pane.is_remote and pane.sftp_manager:
                return pane.sftp_manager
        return self.sftp_manager  # last resort: shared manager

    # How many transfers to enqueue per event-loop tick (keeps UI responsive)
    _ENQUEUE_BATCH_SIZE = 3

    def upload_files(self, local_paths: List[str], remote_dir: str, sftp=None,
                     refresh_pane=None):
        """Upload files and directories.

        Each path becomes a single transfer task — directories are handled
        entirely in the worker thread (walking, mkdir, uploading) so the
        UI never freezes.

        Enqueuing is done in small batches via QTimer so the event loop can
        process repaints between groups, keeping the mouse responsive.

        Args:
            local_paths: Local file/directory paths to upload.
            remote_dir: Remote destination directory.
            sftp: Specific SFTPManager to use (otherwise auto-detected).
            refresh_pane: Pane to refresh on completion (otherwise remote_pane).
        """
        logger.info(f"upload_files called: {len(local_paths)} paths -> {remote_dir}")
        if not local_paths:
            return

        resolved_sftp = self._get_sftp(sftp)
        if not resolved_sftp:
            QMessageBox.warning(self, "Not Connected",
                                "SFTP is not available. Please connect first.")
            return

        # Build the work list then drain it in small batches
        pending = [
            (lp, f"{remote_dir}/{os.path.basename(lp)}", os.path.basename(lp))
            for lp in local_paths
        ]
        self._drain_upload_batch(pending, resolved_sftp, refresh_pane)

    def _drain_upload_batch(self, pending, sftp, refresh_pane):
        """Enqueue up to _ENQUEUE_BATCH_SIZE uploads, then yield to the
        event loop before processing the next batch."""
        batch = pending[:self._ENQUEUE_BATCH_SIZE]
        remaining = pending[self._ENQUEUE_BATCH_SIZE:]
        try:
            for local_path, remote_path, filename in batch:
                self._enqueue_single_upload(
                    local_path, remote_path, filename, 0,
                    sftp=sftp, refresh_pane=refresh_pane
                )
        except Exception as e:
            logger.error(f"Upload error: {e}")
            QMessageBox.critical(self, "Upload Error", str(e))
            return
        if remaining:
            QTimer.singleShot(0, lambda: self._drain_upload_batch(
                remaining, sftp, refresh_pane))

    def _enqueue_single_upload(self, local_path: str, remote_path: str,
                               display_name: str, file_size: int,
                               sftp=None, refresh_pane=None):
        """Create a TransferTask for a single file or directory upload."""
        transfer_id = str(uuid.uuid4())
        transfer = TransferTask(
            task_id=transfer_id, filename=display_name,
            source_path=local_path,
            destination_path=remote_path,
            is_upload=True, total_bytes=file_size, status="pending"
        )
        self.transfer_queue.add_transfer(transfer)
        self.transfer_box.add_transfer(transfer)
        self._enqueue_transfer(transfer_id, "upload", local_path, remote_path,
                               sftp=sftp, refresh_pane=refresh_pane)

    def download_files(self, remote_paths: List[str], local_dir: str, sftp=None,
                       refresh_pane=None):
        """Download files and directories.

        Stats all remote paths in a background thread to avoid freezing the
        UI, then enqueues each as a single transfer task.

        Args:
            remote_paths: Remote file/directory paths to download.
            local_dir: Local destination directory.
            sftp: Specific SFTPManager to use (otherwise auto-detected).
            refresh_pane: Pane to refresh on completion (otherwise local_pane).
        """
        if not remote_paths:
            return

        resolved_sftp = self._get_sftp(sftp)
        if not resolved_sftp:
            QMessageBox.warning(self, "Not Connected",
                                "SFTP is not available. Please connect first.")
            return

        # Store the resolved SFTP and refresh pane for use in the callback
        self._download_sftp = resolved_sftp
        self._download_refresh_pane = refresh_pane

        # Run stat calls in background so the UI stays responsive
        worker = _DownloadStatWorker(resolved_sftp, remote_paths, local_dir)
        thread = QThread()
        worker.moveToThread(thread)

        worker.batch_complete.connect(self._on_download_stats_ready)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        thread.finished.connect(lambda: (worker.deleteLater(), thread.deleteLater()))

        # Store refs to prevent garbage collection
        self._stat_worker = worker
        self._stat_thread = thread

        thread.start()

    def _on_download_stats_ready(self, results: list, local_dir: str):
        """Called on the main thread after background stat calls finish.

        Enqueues one transfer task per path in small batches so the event
        loop stays responsive when many files are queued at once.
        """
        resolved_sftp = getattr(self, '_download_sftp', None)
        refresh_pane = getattr(self, '_download_refresh_pane', None)

        # Build a work list of (remote_path, local_path, display_name, size)
        pending = []
        for remote_path, is_dir, file_size, filename in results:
            local_path = os.path.join(local_dir, filename)
            if is_dir:
                pending.append((remote_path, local_path, f"{filename}/", 0))
            else:
                pending.append((remote_path, local_path, filename, file_size))

        self._drain_download_batch(pending, resolved_sftp, refresh_pane)

    def _drain_download_batch(self, pending, sftp, refresh_pane):
        """Enqueue up to _ENQUEUE_BATCH_SIZE downloads, then yield to the
        event loop before processing the next batch."""
        batch = pending[:self._ENQUEUE_BATCH_SIZE]
        remaining = pending[self._ENQUEUE_BATCH_SIZE:]
        try:
            for remote_path, local_path, display_name, file_size in batch:
                self._enqueue_single_download(
                    remote_path, local_path, display_name, file_size,
                    sftp=sftp, refresh_pane=refresh_pane
                )
        except Exception as e:
            logger.error(f"Download error: {e}")
            QMessageBox.critical(self, "Download Error", str(e))
            return
        if remaining:
            QTimer.singleShot(0, lambda: self._drain_download_batch(
                remaining, sftp, refresh_pane))

    def _enqueue_single_download(self, remote_path: str, local_path: str,
                                 display_name: str, file_size: int,
                                 sftp=None, refresh_pane=None):
        """Create a TransferTask for a single file or directory download."""
        transfer_id = str(uuid.uuid4())
        transfer = TransferTask(
            task_id=transfer_id, filename=display_name,
            source_path=remote_path,
            destination_path=local_path,
            is_upload=False, total_bytes=file_size, status="pending"
        )
        self.transfer_queue.add_transfer(transfer)
        self.transfer_box.add_transfer(transfer)
        self._enqueue_transfer(transfer_id, "download", local_path, remote_path,
                               sftp=sftp, refresh_pane=refresh_pane)

    # ── Concurrency management ──

    def _enqueue_transfer(self, transfer_id: str, direction: str,
                          local_path: str, remote_path: str,
                          sftp=None, refresh_pane=None):
        """Start transfer immediately if under limit, otherwise queue it."""
        if self._active_count < self._max_concurrent:
            self._launch_transfer(transfer_id, direction, local_path, remote_path,
                                  sftp=sftp, refresh_pane=refresh_pane)
        else:
            self._pending_starts.append(
                (transfer_id, direction, local_path, remote_path, sftp, refresh_pane)
            )
            logger.debug(
                f"Transfer {transfer_id} queued ({self._active_count} active, "
                f"{len(self._pending_starts)} pending)"
            )

    def _launch_transfer(self, transfer_id: str, direction: str,
                         local_path: str, remote_path: str,
                         sftp=None, refresh_pane=None):
        """Actually start a transfer worker."""
        self._active_count += 1
        if direction == "upload":
            self._start_upload_worker(transfer_id, local_path, remote_path,
                                      sftp=sftp, refresh_pane=refresh_pane)
        else:
            self._start_download_worker(transfer_id, remote_path, local_path,
                                        sftp=sftp, refresh_pane=refresh_pane)

    def _start_next_pending(self):
        """Start the next pending transfer if a slot is available."""
        while self._pending_starts and self._active_count < self._max_concurrent:
            entry = self._pending_starts.pop(0)
            transfer_id, direction, local_path, remote_path = entry[:4]
            sftp = entry[4] if len(entry) > 4 else None
            refresh_pane = entry[5] if len(entry) > 5 else None
            # Skip if already cancelled while waiting
            if transfer_id in self.transfer_queue.transfers:
                t = self.transfer_queue.transfers[transfer_id]
                if t.status == "cancelled":
                    continue
            self._launch_transfer(transfer_id, direction, local_path, remote_path,
                                  sftp=sftp, refresh_pane=refresh_pane)

    def _start_upload_worker(self, transfer_id: str, local_path: str, remote_path: str,
                             sftp=None, refresh_pane=None):
        """Spin up a background thread for a single file upload."""
        try:
            # Don't stat the file here — the worker thread will determine the
            # actual size when it starts.  Keeping the main thread free avoids
            # freezing the UI on slow file systems.
            file_size = 0

            # Create the models/transfer.TransferTask for TransferWorker
            model_task = ModelTransferTask(
                direction=TransferDirection.UPLOAD,
                local_path=local_path,
                remote_path=remote_path,
                total_bytes=file_size,
                id=transfer_id,
            )

            # Use the explicitly provided SFTP, or fall back to auto-detect
            use_sftp = sftp or self._get_sftp()

            # Create worker and thread
            worker = TransferWorker(use_sftp, model_task)
            thread = QThread()
            worker.moveToThread(thread)

            # Connect worker signals to UI updates
            worker.progress.connect(self._on_transfer_progress)
            worker.speed_updated.connect(self._on_transfer_speed)
            # Refresh the correct pane on completion
            _refresh = refresh_pane
            worker.transfer_completed.connect(
                lambda tid, success: self._on_transfer_done(
                    tid, success, refresh_pane=_refresh)
            )
            worker.transfer_started.connect(self._on_transfer_started)

            # Thread lifecycle — deleteLater after quit to avoid C++ object deletion race
            thread.started.connect(worker.run)
            worker.finished.connect(thread.quit)
            thread.finished.connect(lambda: self._cleanup_transfer_thread(transfer_id))

            # Store references so they aren't garbage collected
            self.transfer_threads[transfer_id] = thread
            self.transfer_workers[transfer_id] = worker

            thread.start()
        except Exception as e:
            logger.error(f"Failed to start upload worker: {e}")
            self.transfer_queue.mark_completed(transfer_id, False)
            self.transfer_box.mark_completed(transfer_id, False)

    def _start_download_worker(self, transfer_id: str, remote_path: str, local_path: str,
                               sftp=None, refresh_pane=None):
        """Spin up a background thread for a single file download."""
        try:
            # Use the explicitly provided SFTP, or fall back to auto-detect
            use_sftp = sftp or self._get_sftp()

            # Don't stat the remote file here — the _DownloadStatWorker
            # already retrieved sizes, and the worker thread will handle
            # any remaining unknowns.  Avoids blocking the main thread
            # with an SFTP round-trip.
            file_size = 0

            # Create the models/transfer.TransferTask for TransferWorker
            model_task = ModelTransferTask(
                direction=TransferDirection.DOWNLOAD,
                local_path=local_path,
                remote_path=remote_path,
                total_bytes=file_size,
                id=transfer_id,
            )

            # Create worker and thread
            worker = TransferWorker(use_sftp, model_task)
            thread = QThread()
            worker.moveToThread(thread)

            # Connect worker signals to UI updates
            worker.progress.connect(self._on_transfer_progress)
            worker.speed_updated.connect(self._on_transfer_speed)
            # Refresh the correct pane on completion
            _refresh = refresh_pane
            worker.transfer_completed.connect(
                lambda tid, success: self._on_transfer_done(
                    tid, success, refresh_pane=_refresh)
            )
            worker.transfer_started.connect(self._on_transfer_started)

            # Thread lifecycle — deleteLater after quit to avoid C++ object deletion race
            thread.started.connect(worker.run)
            worker.finished.connect(thread.quit)
            thread.finished.connect(lambda: self._cleanup_transfer_thread(transfer_id))

            # Store references so they aren't garbage collected
            self.transfer_threads[transfer_id] = thread
            self.transfer_workers[transfer_id] = worker

            thread.start()
        except Exception as e:
            logger.error(f"Failed to start download worker: {e}")
            self.transfer_queue.mark_completed(transfer_id, False)
            self.transfer_box.mark_completed(transfer_id, False)

    def _cleanup_transfer_thread(self, transfer_id: str):
        """Clean up after a transfer finishes, then kick off the next queued one."""
        worker = self.transfer_workers.pop(transfer_id, None)
        thread = self.transfer_threads.pop(transfer_id, None)
        if worker:
            worker.deleteLater()
        if thread:
            thread.deleteLater()

        # Free up a concurrency slot and start next pending transfer
        self._active_count = max(0, self._active_count - 1)
        self._start_next_pending()

    # ── Transfer signal handlers ──

    def _on_transfer_started(self, transfer_id: str):
        """Handle transfer started signal from worker."""
        if transfer_id in self.transfer_queue.transfers:
            self.transfer_queue.transfers[transfer_id].status = "in_progress"
            self.transfer_queue.transfers[transfer_id].start_time = datetime.now()
            if transfer_id in self.transfer_queue.transfer_widgets:
                self.transfer_queue.transfer_widgets[transfer_id].set_status("in_progress")

    def _on_transfer_progress(self, transfer_id: str, bytes_done: int, bytes_total: int):
        """Handle progress signal from worker."""
        self.transfer_queue.update_progress(transfer_id, bytes_done, bytes_total)
        self.transfer_box.update_progress(transfer_id, bytes_done, bytes_total)

    def _on_transfer_speed(self, transfer_id: str, speed_bps: float):
        """Handle speed update signal from worker."""
        self.transfer_queue.update_speed(transfer_id, speed_bps)
        self.transfer_box.update_speed(transfer_id, speed_bps)

    def _on_transfer_done(self, transfer_id: str, success: bool,
                          refresh_pane=None):
        """Called when a transfer finishes. Don't touch thread/worker refs here —
        the thread is still winding down. Actual cleanup happens in
        _cleanup_transfer_thread once thread.finished fires.

        Args:
            transfer_id: ID of the completed transfer.
            success: Whether the transfer succeeded.
            refresh_pane: Specific pane to refresh, or None for no auto-refresh.
        """
        self.transfer_queue.mark_completed(transfer_id, success)
        self.transfer_box.mark_completed(transfer_id, success)

        # Refresh the appropriate pane
        if success and refresh_pane is not None:
            refresh_pane.refresh()

        # Check for pending cluster-to-cluster uploads
        if success and hasattr(self, '_c2c_pending') and self._c2c_pending:
            self._check_c2c_completion(transfer_id)

    def _on_open_remote_file(self, remote_path: str):
        """Download a remote file to /tmp and open it with the default app."""
        sftp = self._get_sftp()
        if not sftp:
            QMessageBox.warning(self, "Not Connected",
                                "SFTP is not available. Please connect first.")
            return

        filename = remote_path.rsplit('/', 1)[-1]
        if not filename:
            return

        # Create a persistent temp directory (not auto-deleted) for opened files
        temp_dir = os.path.join(tempfile.gettempdir(), 'transfpro_open')
        os.makedirs(temp_dir, exist_ok=True)
        local_path = os.path.join(temp_dir, filename)

        # Start a download that opens the file on completion
        transfer_id = str(uuid.uuid4())

        # Don't stat the remote file here — let the worker thread handle
        # it to avoid blocking the main thread with an SFTP round-trip.
        file_size = 0

        transfer = TransferTask(
            task_id=transfer_id, filename=filename,
            source_path=remote_path,
            destination_path=local_path,
            is_upload=False, total_bytes=file_size, status="pending"
        )

        self.transfer_queue.add_transfer(transfer)
        self.transfer_box.add_transfer(transfer)

        # Create the worker/thread for download
        model_task = ModelTransferTask(
            direction=TransferDirection.DOWNLOAD,
            local_path=local_path,
            remote_path=remote_path,
            total_bytes=file_size,
            id=transfer_id,
        )

        worker = TransferWorker(sftp, model_task)
        thread = QThread()
        worker.moveToThread(thread)

        worker.progress.connect(self._on_transfer_progress)
        worker.speed_updated.connect(self._on_transfer_speed)
        worker.transfer_started.connect(self._on_transfer_started)

        # On completion, open the file if successful
        def on_open_transfer_done(tid, success):
            self._on_transfer_done(tid, success)
            if success:
                self._open_file_locally(local_path)

        worker.transfer_completed.connect(on_open_transfer_done)

        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        thread.finished.connect(lambda: self._cleanup_transfer_thread(transfer_id))

        self.transfer_threads[transfer_id] = thread
        self.transfer_workers[transfer_id] = worker
        self._active_count += 1

        thread.start()

    def _open_file_locally(self, local_path: str):
        """Open a file with the OS default app (non-blocking)."""
        try:
            if sys.platform == 'darwin':
                # Use Popen (non-blocking) instead of subprocess.run which
                # can block the main thread for up to the timeout duration.
                subprocess.Popen(['open', local_path],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            elif sys.platform.startswith('linux'):
                subprocess.Popen(['xdg-open', local_path],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            else:
                os.startfile(local_path)
        except Exception as e:
            logger.error(f"Failed to open file locally: {e}")
            QMessageBox.warning(self, "Open Error", f"Could not open file: {e}")

    def _on_open_remote_with(self, remote_path: str, app_path: str):
        """Download a remote file to temp and open it with a specific app."""
        sftp = self._get_sftp()
        if not sftp:
            QMessageBox.warning(self, "Not Connected",
                                "SFTP is not available. Please connect first.")
            return

        filename = remote_path.rsplit('/', 1)[-1]
        if not filename:
            return

        temp_dir = os.path.join(tempfile.gettempdir(), 'transfpro_open')
        os.makedirs(temp_dir, exist_ok=True)
        local_path = os.path.join(temp_dir, filename)

        transfer_id = str(uuid.uuid4())

        # Don't stat the remote file here — let the worker thread handle
        # it to avoid blocking the main thread with an SFTP round-trip.
        file_size = 0

        transfer = TransferTask(
            task_id=transfer_id, filename=filename,
            source_path=remote_path,
            destination_path=local_path,
            is_upload=False, total_bytes=file_size, status="pending"
        )

        self.transfer_queue.add_transfer(transfer)
        self.transfer_box.add_transfer(transfer)

        model_task = ModelTransferTask(
            direction=TransferDirection.DOWNLOAD,
            local_path=local_path,
            remote_path=remote_path,
            total_bytes=file_size,
            id=transfer_id,
        )

        worker = TransferWorker(sftp, model_task)
        thread = QThread()
        worker.moveToThread(thread)

        worker.progress.connect(self._on_transfer_progress)
        worker.speed_updated.connect(self._on_transfer_speed)
        worker.transfer_started.connect(self._on_transfer_started)

        def on_open_with_done(tid, success):
            self._on_transfer_done(tid, success)
            if success:
                self._open_file_with_app(local_path, app_path)

        worker.transfer_completed.connect(on_open_with_done)

        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        thread.finished.connect(lambda: self._cleanup_transfer_thread(transfer_id))

        self.transfer_threads[transfer_id] = thread
        self.transfer_workers[transfer_id] = worker
        self._active_count += 1

        thread.start()

    def _open_file_with_app(self, local_path: str, app_path: str):
        """Open a local file with a specific application."""
        try:
            if sys.platform == 'darwin':
                subprocess.Popen(['open', '-a', app_path, local_path])
            elif sys.platform.startswith('linux'):
                subprocess.Popen([app_path, local_path])
            else:
                subprocess.Popen([app_path, local_path])
        except Exception as e:
            logger.error(f"Failed to open file with {app_path}: {e}")
            QMessageBox.warning(self, "Open Error",
                                f"Could not open file with {app_path}: {e}")

    def _on_pause_requested(self, transfer_id: str):
        self.transfer_queue.pause_transfer(transfer_id)

    def _on_cancel_requested(self, transfer_id: str):
        self.transfer_queue.cancel_transfer(transfer_id)
        self.transfer_box.cancel_transfer(transfer_id)

        # Remove from pending queue if it hasn't started yet
        self._pending_starts = [
            entry for entry in self._pending_starts
            if entry[0] != transfer_id
        ]

        # Cancel the worker (sets is_cancelled flag)
        if transfer_id in self.transfer_workers:
            try:
                self.transfer_workers[transfer_id].cancel()
            except RuntimeError:
                pass

        # Request the thread to quit — cleanup happens in _cleanup_transfer_thread
        if transfer_id in self.transfer_threads:
            thread = self.transfer_threads[transfer_id]
            if thread.isRunning():
                thread.quit()

    def _on_cancel_all_requested(self):
        """Cancel all active and pending transfers."""
        # Collect all non-terminal transfer IDs
        ids_to_cancel = [
            tid for tid, t in self.transfer_box.transfers.items()
            if t.status in ("pending", "in_progress")
        ]
        for tid in ids_to_cancel:
            self._on_cancel_requested(tid)

    def closeEvent(self, event):
        if getattr(self, '_shutdown_done', False):
            # MainWindow already cleaned everything up — skip waits.
            super().closeEvent(event)
            return

        # Standalone close (tab destroyed independently)
        for worker in list(self.transfer_workers.values()):
            try:
                worker.cancel()
            except RuntimeError:
                pass
        for thread in list(self.transfer_threads.values()):
            if thread.isRunning():
                thread.quit()
        import time
        deadline = time.monotonic() + 0.5
        for thread in list(self.transfer_threads.values()):
            remaining = max(0, int((deadline - time.monotonic()) * 1000))
            if thread.isRunning() and remaining > 0:
                if not thread.wait(remaining):
                    thread.terminate()
        self.transfer_threads.clear()
        self.transfer_workers.clear()

        if hasattr(self, 'local_pane'):
            self.local_pane.cleanup_browser_thread()
        if hasattr(self, 'remote_pane'):
            self.remote_pane.cleanup_browser_thread()

        if hasattr(self, 'local_terminal'):
            self.local_terminal.disconnect_terminal()
        if hasattr(self, 'remote_terminal'):
            self.remote_terminal.disconnect_terminal()

        super().closeEvent(event)
