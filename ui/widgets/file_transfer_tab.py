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

        self._update_header()
        self._resize_to_fit()
        self.show()
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

    def __init__(self, ssh_manager, sftp_manager, database, parent=None):
        super().__init__(parent)
        self.ssh_manager = ssh_manager
        self.sftp_manager = sftp_manager
        self.database = database
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
        """Build the split-pane layout: local browser + terminal | remote browser + terminal."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # MAIN CONTENT — horizontal splitter, 50/50
        self.main_splitter = QSplitter(Qt.Horizontal)

        # ── Left column: local file browser + local terminal ──
        self.local_vsplitter = QSplitter(Qt.Vertical)

        self.local_pane = FileBrowserPane(
            title="Local",
            is_remote=False,
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

        # ── Right column: remote file browser + remote terminal ──
        self.remote_vsplitter = QSplitter(Qt.Vertical)

        self.remote_pane = FileBrowserPane(
            title="Remote",
            is_remote=True,
            sftp_manager=self.sftp_manager,
            parent=self
        )
        self.remote_vsplitter.addWidget(self.remote_pane)

        self.remote_terminal = MiniTerminal(
            is_remote=True,
            ssh_manager=self.ssh_manager,
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
        self.local_pane.transfer_upload_requested.connect(
            lambda paths, target: self.upload_files(paths, target))
        self.local_pane.transfer_download_requested.connect(
            lambda paths, target: self.download_files(paths, target))
        self.remote_pane.transfer_upload_requested.connect(
            lambda paths, target: self.upload_files(paths, target))
        self.remote_pane.transfer_download_requested.connect(
            lambda paths, target: self.download_files(paths, target))
        self.local_pane.transfer_button_clicked.connect(self._on_upload_clicked)
        self.remote_pane.transfer_button_clicked.connect(self._on_download_clicked)
        # Quick Transfer Macros — both panes emit the same signal
        self.local_pane.transfer_macro_requested.connect(self._on_transfer_macro)
        self.remote_pane.transfer_macro_requested.connect(self._on_transfer_macro)
        self.remote_pane.open_remote_file_requested.connect(self._on_open_remote_file)
        self.remote_pane.open_remote_with_requested.connect(self._on_open_remote_with)
        # Keep mini-terminal cwd in sync when navigating the file browser
        self.local_pane.directory_changed.connect(self.local_terminal.cd)
        self.remote_pane.directory_changed.connect(self.remote_terminal.cd)
        self.transfer_queue.pause_requested.connect(self._on_pause_requested)
        self.transfer_queue.cancel_requested.connect(self._on_cancel_requested)

    # ── Button handlers ──

    def _on_upload_clicked(self):
        selected_paths = self.local_pane.get_selected_paths()
        if not selected_paths:
            QMessageBox.information(self, "No Files Selected",
                                   "Please select files to upload")
            return
        self.upload_files(selected_paths, self.remote_pane.current_path)

    def _on_download_clicked(self):
        selected_paths = self.remote_pane.get_selected_paths()
        if not selected_paths:
            QMessageBox.information(self, "No Files Selected",
                                   "Please select files to download")
            return
        self.download_files(selected_paths, self.local_pane.current_path)

    def _on_transfer_macro(self, local_path: str, remote_path: str, direction: str):
        """Execute a quick transfer macro."""
        if direction == 'upload':
            self.upload_files([local_path], remote_path)
        else:
            self.download_files([remote_path], local_path)

    # ── Transfer logic ──

    def upload_files(self, local_paths: List[str], remote_dir: str):
        """Upload files and directories.

        Each path becomes a single transfer task — directories are handled
        entirely in the worker thread (walking, mkdir, uploading) so the
        UI never freezes.
        """
        logger.info(f"upload_files called: {len(local_paths)} paths -> {remote_dir}")
        if not local_paths:
            return

        if not self.sftp_manager:
            QMessageBox.warning(self, "Not Connected",
                                "SFTP is not available. Please connect first.")
            return

        try:
            valid_paths = [p for p in local_paths if os.path.exists(p)]
            if not valid_paths:
                QMessageBox.warning(self, "Error", "No valid files to upload")
                return

            for local_path in valid_paths:
                filename = os.path.basename(local_path)

                if os.path.isdir(local_path):
                    # Directory → single task; worker handles everything
                    self._enqueue_single_upload(
                        local_path, f"{remote_dir}/{filename}",
                        f"{filename}/", 0  # total_bytes computed by worker
                    )
                else:
                    file_size = os.path.getsize(local_path)
                    self._enqueue_single_upload(
                        local_path, f"{remote_dir}/{filename}",
                        filename, file_size
                    )
        except Exception as e:
            logger.error(f"Upload error: {e}")
            QMessageBox.critical(self, "Upload Error", str(e))

    def _enqueue_single_upload(self, local_path: str, remote_path: str,
                               display_name: str, file_size: int):
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
        self._enqueue_transfer(transfer_id, "upload", local_path, remote_path)

    def download_files(self, remote_paths: List[str], local_dir: str):
        """Download files and directories.

        Stats all remote paths in a background thread to avoid freezing the
        UI, then enqueues each as a single transfer task.
        """
        if not remote_paths:
            return

        if not self.sftp_manager:
            QMessageBox.warning(self, "Not Connected",
                                "SFTP is not available. Please connect first.")
            return

        # Run stat calls in background so the UI stays responsive
        worker = _DownloadStatWorker(self.sftp_manager, remote_paths, local_dir)
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

        Enqueues one transfer task per path, now that we know file sizes
        and which paths are directories.
        """
        try:
            for remote_path, is_dir, file_size, filename in results:
                if is_dir:
                    local_path = os.path.join(local_dir, filename)
                    self._enqueue_single_download(
                        remote_path, local_path,
                        f"{filename}/", 0  # total_bytes computed by worker
                    )
                else:
                    local_path = os.path.join(local_dir, filename)
                    self._enqueue_single_download(
                        remote_path, local_path, filename, file_size
                    )
        except Exception as e:
            logger.error(f"Download error: {e}")
            QMessageBox.critical(self, "Download Error", str(e))

    def _enqueue_single_download(self, remote_path: str, local_path: str,
                                 display_name: str, file_size: int):
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
        self._enqueue_transfer(transfer_id, "download", local_path, remote_path)

    # ── Concurrency management ──

    def _enqueue_transfer(self, transfer_id: str, direction: str,
                          local_path: str, remote_path: str):
        """Start transfer immediately if under limit, otherwise queue it."""
        if self._active_count < self._max_concurrent:
            self._launch_transfer(transfer_id, direction, local_path, remote_path)
        else:
            self._pending_starts.append((transfer_id, direction, local_path, remote_path))
            logger.debug(
                f"Transfer {transfer_id} queued ({self._active_count} active, "
                f"{len(self._pending_starts)} pending)"
            )

    def _launch_transfer(self, transfer_id: str, direction: str,
                         local_path: str, remote_path: str):
        """Actually start a transfer worker."""
        self._active_count += 1
        if direction == "upload":
            self._start_upload_worker(transfer_id, local_path, remote_path)
        else:
            self._start_download_worker(transfer_id, remote_path, local_path)

    def _start_next_pending(self):
        """Start the next pending transfer if a slot is available."""
        while self._pending_starts and self._active_count < self._max_concurrent:
            transfer_id, direction, local_path, remote_path = self._pending_starts.pop(0)
            # Skip if already cancelled while waiting
            if transfer_id in self.transfer_queue.transfers:
                t = self.transfer_queue.transfers[transfer_id]
                if t.status == "cancelled":
                    continue
            self._launch_transfer(transfer_id, direction, local_path, remote_path)

    def _start_upload_worker(self, transfer_id: str, local_path: str, remote_path: str):
        """Spin up a background thread for a single file upload."""
        try:
            # Get file size for the model task
            file_size = os.path.getsize(local_path) if os.path.isfile(local_path) else 0

            # Create the models/transfer.TransferTask for TransferWorker
            model_task = ModelTransferTask(
                direction=TransferDirection.UPLOAD,
                local_path=local_path,
                remote_path=remote_path,
                total_bytes=file_size,
                id=transfer_id,
            )

            # Create worker and thread
            worker = TransferWorker(self.sftp_manager, model_task)
            thread = QThread()
            worker.moveToThread(thread)

            # Connect worker signals to UI updates
            worker.progress.connect(self._on_transfer_progress)
            worker.speed_updated.connect(self._on_transfer_speed)
            worker.transfer_completed.connect(
                lambda tid, success: self._on_transfer_done(tid, success, refresh_remote=True)
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

    def _start_download_worker(self, transfer_id: str, remote_path: str, local_path: str):
        """Spin up a background thread for a single file download."""
        try:
            # Get file size from remote
            file_size = 0
            try:
                metadata = self.sftp_manager.get_file_info(remote_path)
                file_size = metadata.size if metadata else 0
            except Exception:
                pass

            # Create the models/transfer.TransferTask for TransferWorker
            model_task = ModelTransferTask(
                direction=TransferDirection.DOWNLOAD,
                local_path=local_path,
                remote_path=remote_path,
                total_bytes=file_size,
                id=transfer_id,
            )

            # Create worker and thread
            worker = TransferWorker(self.sftp_manager, model_task)
            thread = QThread()
            worker.moveToThread(thread)

            # Connect worker signals to UI updates
            worker.progress.connect(self._on_transfer_progress)
            worker.speed_updated.connect(self._on_transfer_speed)
            worker.transfer_completed.connect(
                lambda tid, success: self._on_transfer_done(tid, success, refresh_remote=False)
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

    def _on_transfer_done(self, transfer_id: str, success: bool, refresh_remote: bool = True):
        """Called when a transfer finishes. Don't touch thread/worker refs here —
        the thread is still winding down. Actual cleanup happens in
        _cleanup_transfer_thread once thread.finished fires."""
        self.transfer_queue.mark_completed(transfer_id, success)
        self.transfer_box.mark_completed(transfer_id, success)

        # Refresh the appropriate pane
        if success:
            if refresh_remote:
                self.remote_pane.refresh()
            else:
                self.local_pane.refresh()

    def _on_open_remote_file(self, remote_path: str):
        """Download a remote file to /tmp and open it with the default app."""
        if not self.sftp_manager:
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

        file_size = 0
        try:
            metadata = self.sftp_manager.get_file_info(remote_path)
            file_size = metadata.size if metadata else 0
        except Exception as e:
            logger.debug(f"Could not stat {remote_path}: {e}")

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

        worker = TransferWorker(self.sftp_manager, model_task)
        thread = QThread()
        worker.moveToThread(thread)

        worker.progress.connect(self._on_transfer_progress)
        worker.speed_updated.connect(self._on_transfer_speed)
        worker.transfer_started.connect(self._on_transfer_started)

        # On completion, open the file if successful
        def on_open_transfer_done(tid, success):
            self._on_transfer_done(tid, success, refresh_remote=False)
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
        """Open a file with the OS default app (macOS 'open', Linux 'xdg-open')."""
        try:
            if sys.platform == 'darwin':
                # Try 'open' first — if no app is registered, it returns non-zero
                result = subprocess.run(
                    ['open', local_path],
                    capture_output=True, timeout=5
                )
                if result.returncode != 0:
                    # Fallback: open with TextEdit for unrecognized file types
                    subprocess.Popen(['open', '-a', 'TextEdit', local_path])
            elif sys.platform.startswith('linux'):
                subprocess.Popen(['xdg-open', local_path])
            else:
                os.startfile(local_path)
        except Exception as e:
            logger.error(f"Failed to open file locally: {e}")
            QMessageBox.warning(self, "Open Error", f"Could not open file: {e}")

    def _on_open_remote_with(self, remote_path: str, app_path: str):
        """Download a remote file to temp and open it with a specific app."""
        if not self.sftp_manager:
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

        file_size = 0
        try:
            metadata = self.sftp_manager.get_file_info(remote_path)
            file_size = metadata.size if metadata else 0
        except Exception as e:
            logger.debug(f"Could not stat {remote_path}: {e}")

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

        worker = TransferWorker(self.sftp_manager, model_task)
        thread = QThread()
        worker.moveToThread(thread)

        worker.progress.connect(self._on_transfer_progress)
        worker.speed_updated.connect(self._on_transfer_speed)
        worker.transfer_started.connect(self._on_transfer_started)

        def on_open_with_done(tid, success):
            self._on_transfer_done(tid, success, refresh_remote=False)
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
