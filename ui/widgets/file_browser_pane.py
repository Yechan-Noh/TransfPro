"""
File Browser Pane widget for local and remote filesystem browsing.

This module provides a single-pane file browser that works for both local
and remote filesystems with full features including drag-and-drop, context
menus, bookmarks, and comprehensive file operations.
"""

import logging
import os
import json
import stat as stat_module
import subprocess
import time as _time
from typing import List, Optional, Dict
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QTreeWidget,
    QTreeWidgetItem, QHeaderView, QMenu, QMessageBox, QInputDialog,
    QFileDialog, QLabel, QCheckBox, QComboBox, QFrame, QSplitter,
    QApplication, QFileIconProvider
)
from PyQt5.QtCore import Qt, pyqtSignal, QMimeData, QUrl, QTimer, QSize, QThread, QSettings, QEvent
from PyQt5.QtGui import QIcon, QDrag, QFont, QColor, QPixmap, QPainter, QPen
from PyQt5.QtWidgets import QShortcut
from PyQt5.QtGui import QKeySequence
import fnmatch

try:
    from transfpro.core.gromacs_parser import (
        GROMACS_EXTENSIONS, GROMACS_INPUT_EXTENSIONS, GROMACS_OUTPUT_EXTENSIONS
    )
except ImportError:
    GROMACS_EXTENSIONS = set()
    GROMACS_INPUT_EXTENSIONS = set()
    GROMACS_OUTPUT_EXTENSIONS = set()
from transfpro.workers.remote_browser_worker import RemoteBrowserWorker

logger = logging.getLogger(__name__)


class _LocalListWorker(QThread):
    """Background thread that runs os.scandir and collects metadata
    so the main thread doesn't freeze on large local directories."""

    listing_ready = pyqtSignal(str, list)   # path, list of tuples
    error = pyqtSignal(str)

    def __init__(self, path: str, show_hidden: bool):
        super().__init__()
        self._path = path
        self._show_hidden = show_hidden

    def run(self):
        try:
            if not os.path.isdir(self._path):
                self.error.emit(f"Not a directory: {self._path}")
                return
            entries = []
            try:
                scanner = os.scandir(self._path)
            except PermissionError:
                self.error.emit(f"Cannot access directory: {self._path}")
                return
            with scanner:
                for entry in scanner:
                    name = entry.name
                    if not self._show_hidden and name[0] == '.':
                        continue
                    try:
                        st = entry.stat(follow_symlinks=True)
                    except (OSError, PermissionError):
                        continue
                    is_dir = stat_module.S_ISDIR(st.st_mode)
                    is_symlink = entry.is_symlink()
                    size = 0 if is_dir else st.st_size
                    mtime = st.st_mtime
                    perm_str = oct(st.st_mode)[-3:]
                    entries.append((name, entry.path, is_dir, size, mtime, perm_str, is_symlink))
            self.listing_ready.emit(self._path, entries)
        except Exception as e:
            self.error.emit(str(e))

# MIME type for internal file transfers
TRANSFPRO_FILES_MIME_TYPE = "application/x-transfpro-files"



class DropZoneOverlay(QWidget):
    """Translucent overlay shown when files are dragged over a pane."""

    def __init__(self, parent=None, is_upload=True):
        super().__init__(parent)
        self._is_upload = is_upload
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAutoFillBackground(False)
        self.hide()

    def set_upload(self, is_upload: bool):
        self._is_upload = is_upload
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self._is_upload:
            bg = QColor(14, 165, 233, 40)
            border = QColor(14, 165, 233, 120)
            text = "Drop to Upload  ↑"
        else:
            bg = QColor(166, 218, 149, 40)
            border = QColor(166, 218, 149, 120)
            text = "Drop to Download  ↓"
        painter.fillRect(self.rect(), bg)
        pen = QPen(border, 2.5, Qt.DashLine)
        painter.setPen(pen)
        margin = 12
        painter.drawRoundedRect(
            margin, margin,
            self.width() - 2 * margin,
            self.height() - 2 * margin,
            12, 12
        )
        font = QFont()
        font.setPixelSize(18)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, 200))
        painter.drawText(self.rect(), Qt.AlignCenter, text)
        painter.end()


# Global clipboard for cross-pane copy/paste
_file_clipboard = {'paths': [], 'is_remote': False}


class FileBrowserPane(QWidget):
    """Single file browser pane (local or remote)."""

    files_selected = pyqtSignal(list)  # List[str] - selected file paths
    directory_changed = pyqtSignal(str)  # New directory path
    transfer_requested = pyqtSignal(list, str)  # source paths, target directory
    transfer_upload_requested = pyqtSignal(list, str)   # local paths, remote dir
    transfer_download_requested = pyqtSignal(list, str)  # remote paths, local dir
    transfer_button_clicked = pyqtSignal()  # Upload or Download button pressed
    open_remote_file_requested = pyqtSignal(str)  # remote path to download & open
    open_remote_with_requested = pyqtSignal(str, str)  # remote path, app path
    # Quick Transfer Macro: emits (local_path, remote_path, direction)
    transfer_macro_requested = pyqtSignal(str, str, str)

    # Sorting data roles
    SORT_ROLE = Qt.UserRole + 1
    IS_DIR_ROLE = Qt.UserRole + 2

    def __init__(
        self,
        title: str,
        is_remote: bool = False,
        sftp_manager=None,
        parent=None
    ):
        """
        Initialize the file browser pane.

        Args:
            title: Title for this pane ("Local" or "Remote")
            is_remote: Whether this is a remote browser
            sftp_manager: SFTPManager instance for remote operations
            parent: Parent widget
        """
        super().__init__(parent)
        self.title = title
        self.is_remote = is_remote
        self.sftp_manager = sftp_manager
        self.current_path = os.path.expanduser("~") if not is_remote else "."
        self.show_hidden = False
        self.bookmarks = {}
        self._sort_column = 0
        self._sort_order = Qt.AscendingOrder
        self._total_size_bytes = 0  # Track total size without re-parsing

        # Async remote operation worker/thread
        self._browser_thread = None
        self._browser_worker = None
        self._pending_delete_count = 0
        self._pending_items = []       # Lazy loading overflow
        self._local_list_worker = None  # Background local listing thread


        # Bookmarks
        self._bookmarks = []  # list of (name, path)
        self._load_bookmarks()

        # Quick Transfer Macros
        self._transfer_macros = []  # list of {name, local_path, remote_path, direction}
        self._load_transfer_macros()

        # File filter
        self._filter_text = ''

        # Cache icons — avoid creating QPixmap per file
        self._icon_cache = {}
        self._dir_font = QFont()
        self._dir_font.setBold(True)
        self._dir_color = QColor(140, 160, 255)
        self._size_color = QColor(160, 160, 170)
        self._modified_color = QColor(140, 140, 150)
        self._perm_color = QColor(130, 130, 140)

        self._setup_ui()
        self._connect_signals()
        # Only auto-refresh local pane; remote pane refreshes after connection
        if not self.is_remote:
            self.refresh()

    def _setup_ui(self):
        """Set up the UI with macOS Finder-inspired design."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── TITLE BAR (Finder-style window header with transfer button) ──
        title_bar = QWidget()
        title_bar.setFixedHeight(32)
        title_bar.setStyleSheet("""
            QWidget {
                background: #1e2030;
                border-bottom: 1px solid #363a4f;
            }
        """)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(12, 0, 12, 0)
        title_layout.setSpacing(8)

        transfer_btn_qss = """
            QPushButton {
                background: rgba(14, 165, 233, 0.15);
                border: 1px solid rgba(14, 165, 233, 0.25);
                border-radius: 6px;
                color: #cad3f5;
                padding: 2px 10px;
                font-size: 10px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(14, 165, 233, 0.3);
                border-color: rgba(14, 165, 233, 0.5);
                color: white;
            }
            QPushButton:pressed {
                background: rgba(14, 165, 233, 0.4);
            }
        """

        title_label_qss = """
            color: #cad3f5; font-size: 12px;
            font-weight: 600; letter-spacing: 0.3px;
        """

        if not self.is_remote:
            # Local pane: title centered, Upload button on right edge
            title_layout.addStretch()
            title_label = QLabel(self.title)
            title_label.setStyleSheet(title_label_qss)
            title_layout.addWidget(title_label)
            title_layout.addStretch()

            self.transfer_button = QPushButton("↑ Upload")
            self.transfer_button.setFixedHeight(22)
            self.transfer_button.setStyleSheet(transfer_btn_qss)
            self.transfer_button.setToolTip("Upload selected files to remote")
            self.transfer_button.clicked.connect(self.transfer_button_clicked.emit)
            title_layout.addWidget(self.transfer_button)
        else:
            # Remote pane: Download button on left edge, title centered
            self.transfer_button = QPushButton("↓ Download")
            self.transfer_button.setFixedHeight(22)
            self.transfer_button.setStyleSheet(transfer_btn_qss)
            self.transfer_button.setToolTip("Download selected files to local")
            self.transfer_button.clicked.connect(self.transfer_button_clicked.emit)
            title_layout.addWidget(self.transfer_button)

            title_layout.addStretch()
            title_label = QLabel(self.title)
            title_label.setStyleSheet(title_label_qss)
            title_layout.addWidget(title_label)
            title_layout.addStretch()

        layout.addWidget(title_bar)

        # ── BOOKMARK BAR ──
        self._bookmark_bar = QWidget()
        self._bookmark_bar.setFixedHeight(28)
        self._bookmark_bar.setStyleSheet("""
            QWidget {
                background: #181926;
                border-bottom: 1px solid #363a4f;
            }
        """)
        self._bookmark_bar_layout = QHBoxLayout(self._bookmark_bar)
        self._bookmark_bar_layout.setContentsMargins(8, 2, 8, 2)
        self._bookmark_bar_layout.setSpacing(4)
        self._rebuild_bookmark_buttons()
        layout.addWidget(self._bookmark_bar)

        # ── QUICK TRANSFER MACRO BAR ──
        self._macro_bar = QFrame()
        self._macro_bar.setObjectName("macroBar")
        self._macro_bar.setFixedHeight(28)
        self._macro_bar.setStyleSheet("""
            QFrame#macroBar {
                background: #181926;
                border-bottom: 1px solid #363a4f;
            }
        """)
        self._macro_bar_layout = QHBoxLayout(self._macro_bar)
        self._macro_bar_layout.setContentsMargins(8, 2, 8, 2)
        self._macro_bar_layout.setSpacing(4)
        self._rebuild_macro_buttons()
        layout.addWidget(self._macro_bar)

        # ── TOOLBAR (macOS-style navigation bar) ──
        toolbar = QWidget()
        toolbar.setFixedHeight(40)
        toolbar.setStyleSheet("""
            QWidget {
                background: rgba(30, 32, 48, 0.9);
                border-bottom: 1px solid rgba(54,58,79,0.5);
            }
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(6, 2, 6, 2)
        toolbar_layout.setSpacing(3)

        # Finder-style icon buttons
        nav_btn_qss = """
            QPushButton {
                background: rgba(202,211,245,0.06);
                border: 1px solid #363a4f;
                border-radius: 6px;
                color: #cad3f5;
                padding: 3px 10px;
                font-size: 16px;
                min-width: 32px;
            }
            QPushButton:hover {
                background: rgba(202,211,245,0.12);
                border-color: rgba(202,211,245,0.15);
            }
            QPushButton:pressed {
                background: rgba(14, 165, 233, 0.25);
            }
        """

        self.up_button = QPushButton("◀")
        self.up_button.setFixedSize(38, 32)
        self.up_button.setStyleSheet(nav_btn_qss)
        self.up_button.setToolTip("Go to parent directory")
        toolbar_layout.addWidget(self.up_button)

        self.home_button = QPushButton("⌂")
        self.home_button.setFixedSize(38, 32)
        self.home_button.setStyleSheet(nav_btn_qss)
        self.home_button.setToolTip("Go to home directory")
        toolbar_layout.addWidget(self.home_button)

        self.refresh_button = QPushButton("↻")
        self.refresh_button.setFixedSize(38, 32)
        self.refresh_button.setStyleSheet(nav_btn_qss)
        self.refresh_button.setToolTip("Refresh current directory")
        toolbar_layout.addWidget(self.refresh_button)

        toolbar_layout.addSpacing(6)

        # Path breadcrumb bar (Finder-style)
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Path...")
        self.path_input.setStyleSheet("""
            QLineEdit {
                background: rgba(202,211,245,0.06);
                border: 1px solid #363a4f;
                border-radius: 6px;
                color: #cad3f5;
                padding: 4px 10px;
                font-size: 14px;
                selection-background-color: rgba(14, 165, 233, 0.3);
            }
            QLineEdit:focus {
                border-color: rgba(14, 165, 233, 0.4);
                background: rgba(202,211,245,0.08);
            }
        """)
        toolbar_layout.addWidget(self.path_input, 1)

        toolbar_layout.addSpacing(6)

        # Show hidden toggle
        self.show_hidden_checkbox = QCheckBox("⚙")
        self.show_hidden_checkbox.setToolTip("Show hidden files")
        self.show_hidden_checkbox.setStyleSheet("""
            QCheckBox {
                color: rgba(202,211,245,0.5);
                spacing: 4px;
                font-size: 13px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1px solid rgba(202,211,245,0.15);
                background: rgba(202,211,245,0.06);
            }
            QCheckBox::indicator:checked {
                background: rgba(14, 165, 233, 0.5);
                border-color: rgba(14, 165, 233, 0.7);
            }
        """)
        toolbar_layout.addWidget(self.show_hidden_checkbox)

        layout.addWidget(toolbar)

        # ── FILE LIST (Finder-style column view) ──
        self.file_tree = QTreeWidget()
        self.file_tree.setColumnCount(4)
        self.file_tree.setHeaderLabels(["Name", "Size", "Modified", "Permissions"])
        self.file_tree.setColumnWidth(0, 200)
        self.file_tree.setColumnWidth(1, 80)
        self.file_tree.setColumnWidth(2, 140)
        self.file_tree.setColumnWidth(3, 80)
        self.file_tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.file_tree.setRootIsDecorated(False)
        self.file_tree.setUniformRowHeights(True)
        self.file_tree.setAllColumnsShowFocus(True)
        self.file_tree.setIndentation(0)
        self.file_tree.setStyleSheet("""
            QTreeWidget {
                background: rgba(26, 27, 38, 0.95);
                border: none;
                color: #cad3f5;
                font-size: 12px;
                outline: none;
            }
            QTreeWidget::item {
                padding: 3px 6px;
                border-bottom: 1px solid rgba(54,58,79,0.3);
            }
            QTreeWidget::item:selected {
                background: rgba(14, 165, 233, 0.2);
                color: white;
            }
            QTreeWidget::item:hover {
                background: rgba(202,211,245,0.04);
            }
            QHeaderView::section {
                background: #1e2030;
                color: rgba(202,211,245,0.5);
                border: none;
                border-right: 1px solid rgba(54,58,79,0.3);
                border-bottom: 1px solid #363a4f;
                padding: 5px 8px;
                font-size: 10px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            QHeaderView::section:hover {
                background: rgba(40, 40, 55, 0.95);
                color: rgba(255,255,255,0.7);
            }
            QScrollBar:vertical {
                width: 8px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.12);
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255,255,255,0.2);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

        # Set up sorting — click headers to sort
        self.file_tree.setSortingEnabled(False)  # We handle sorting manually
        header = self.file_tree.header()
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._on_header_clicked)
        # Columns are user-resizable; Name stretches to fill remaining space
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        # Show sort indicator
        header.setSortIndicatorShown(True)
        header.setSortIndicator(0, Qt.AscendingOrder)

        # Enable drag-and-drop between panes
        self.file_tree.setDragEnabled(True)
        self.file_tree.setAcceptDrops(True)
        self.file_tree.setDragDropMode(QTreeWidget.DragDrop)
        self.file_tree.setDefaultDropAction(Qt.CopyAction)
        self.setAcceptDrops(True)

        # ── FILE FILTER BAR ──
        filter_bar = QWidget()
        filter_bar.setFixedHeight(30)
        filter_bar.setStyleSheet("""
            QWidget {
                background: rgba(30, 32, 48, 0.9);
                border-bottom: 1px solid rgba(54,58,79,0.3);
            }
        """)
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(8, 2, 8, 2)
        filter_layout.setSpacing(6)

        filter_icon = QLabel('🔍')
        filter_icon.setStyleSheet('font-size: 12px;')
        filter_layout.addWidget(filter_icon)

        self._filter_input = QLineEdit()
        self._filter_input.setPlaceholderText('Filter files (e.g. *.tpr, md*)...')
        self._filter_input.setStyleSheet("""
            QLineEdit {
                background: rgba(202,211,245,0.06);
                border: 1px solid #363a4f;
                border-radius: 4px;
                color: #cad3f5;
                padding: 2px 8px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border-color: rgba(14, 165, 233, 0.4);
            }
        """)
        self._filter_input.textChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self._filter_input, 1)

        clear_filter_btn = QPushButton('✕')
        clear_filter_btn.setFixedSize(22, 22)
        clear_filter_btn.setStyleSheet("""
            QPushButton { background: transparent; border: none; color: #6e738d; font-size: 11px; }
            QPushButton:hover { color: #cad3f5; }
        """)
        clear_filter_btn.clicked.connect(lambda: self._filter_input.clear())
        filter_layout.addWidget(clear_filter_btn)

        layout.addWidget(filter_bar)

        layout.addWidget(self.file_tree, 1)

        # ── DROP ZONE OVERLAY ──
        self._drop_overlay = DropZoneOverlay(self.file_tree, is_upload=self.is_remote)
        self._drop_overlay.hide()

        # ── STATUS BAR (Finder-style bottom bar) ──
        status_bar = QWidget()
        status_bar.setFixedHeight(28)
        status_bar.setStyleSheet("""
            QWidget {
                background: rgba(25, 25, 38, 0.95);
                border-top: 1px solid rgba(255,255,255,0.04);
            }
        """)
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(10, 0, 10, 0)

        self.status_label = QLabel()
        self.status_label.setStyleSheet("""
            color: rgba(255,255,255,0.4);
            font-size: 13px;
        """)
        self._update_status_bar()
        status_layout.addWidget(self.status_label)

        layout.addWidget(status_bar)

        self.setLayout(layout)

    def _connect_signals(self):
        """Connect signals and slots."""
        self.path_input.returnPressed.connect(self._on_path_entered)
        self.up_button.clicked.connect(self._on_up_clicked)
        self.home_button.clicked.connect(self._on_home_clicked)
        self.refresh_button.clicked.connect(self.refresh)
        self.show_hidden_checkbox.stateChanged.connect(self._on_show_hidden_changed)

        self.file_tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.file_tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.file_tree.customContextMenuRequested.connect(self._on_context_menu)
        self.file_tree.setContextMenuPolicy(Qt.CustomContextMenu)

        # Drag and drop — override startDrag and install an event filter on
        # the viewport to intercept drag/drop events.  Instance-method
        # overrides (file_tree.dropEvent = ...) don't work reliably in PyQt
        # because QAbstractItemView dispatches drag events through the
        # viewport's C++ vtable, which bypasses Python instance attributes.
        self.file_tree.startDrag = self._start_drag
        self.file_tree.viewport().installEventFilter(self)

        # Keyboard shortcuts: Ctrl+C copy, Ctrl+V paste
        copy_sc = QShortcut(QKeySequence.Copy, self)
        copy_sc.activated.connect(self._on_copy_files)
        paste_sc = QShortcut(QKeySequence.Paste, self)
        paste_sc.activated.connect(self._on_paste_files)

    # ── Thread lifecycle ──

    def cleanup_browser_thread(self):
        """Stop and clean up the persistent browser thread.

        Called from parent closeEvent or when the widget is destroyed.
        Uses a short wait since MainWindow already signals threads to
        stop and force-terminates stragglers.
        """
        if self._browser_thread is not None:
            if self._browser_thread.isRunning():
                self._browser_thread.quit()
                if not self._browser_thread.wait(500):
                    self._browser_thread.terminate()
                    self._browser_thread.wait(200)
            if self._browser_worker is not None:
                try:
                    self._browser_worker.deleteLater()
                except RuntimeError:
                    pass
            try:
                self._browser_thread.deleteLater()
            except RuntimeError:
                pass
            self._browser_thread = None
            self._browser_worker = None

    def closeEvent(self, event):
        if getattr(self, '_shutdown_done', False):
            super().closeEvent(event)
            return
        self.cleanup_browser_thread()
        super().closeEvent(event)

    # ── Persistent remote worker (one thread, reused for all ops) ──

    def _ensure_remote_worker(self):
        """Spin up the persistent background thread + worker once."""
        if self._browser_thread is not None and self._browser_thread.isRunning():
            return  # Already alive

        worker = RemoteBrowserWorker(self.sftp_manager)
        thread = QThread()
        worker.moveToThread(thread)

        worker.listing_ready.connect(self._on_listing_ready)
        worker.home_ready.connect(self._on_home_ready)
        worker.operation_done.connect(self._on_remote_op_done)
        worker.file_info_ready.connect(self._on_file_info_ready)
        worker.error.connect(self._on_remote_op_error)

        self._browser_thread = thread
        self._browser_worker = worker
        thread.start()

    def _run_remote_op(self, operation: str, path: str = '', **kwargs):
        """Dispatch a remote SFTP operation to the persistent worker thread."""
        if not self.sftp_manager:
            return

        # Guard: skip if SSH is not connected
        ssh = getattr(self.sftp_manager, 'ssh', None)
        if ssh and hasattr(ssh, 'is_connected') and not ssh.is_connected():
            return

        self._ensure_remote_worker()
        self._browser_worker.request.emit(operation, path, kwargs)

    def _on_listing_ready(self, path: str, metadata_list: list):
        """Handle directory listing result from background worker."""
        try:
            self.current_path = path
            self.path_input.setText(path)

            self.file_tree.setUpdatesEnabled(False)
            self.file_tree.blockSignals(True)
            self.file_tree.clear()

            show_hidden = self.show_hidden
            items = []
            total_size = 0
            get_icon = self._get_file_icon
            format_size = self._format_size
            SORT_ROLE = self.SORT_ROLE
            IS_DIR_ROLE = self.IS_DIR_ROLE

            for metadata in metadata_list:
                name = metadata.name
                if not show_hidden and name.startswith('.'):
                    continue

                is_dir = metadata.is_dir
                is_symlink = getattr(metadata, 'is_symlink', False)
                size = metadata.size
                mtime = metadata.modified
                perm_str = oct(metadata.permissions)[-3:]

                item = QTreeWidgetItem()
                item.setIcon(0, get_icon(name, is_dir))
                display_name = f"{name} \u2192" if is_symlink else name
                item.setText(0, display_name)
                item.setData(0, Qt.UserRole, metadata.path)
                item.setData(0, IS_DIR_ROLE, is_dir)
                item.setData(0, SORT_ROLE, ('0' if is_dir else '1') + name.lower())

                if is_dir:
                    item.setText(1, "—")
                    item.setData(1, SORT_ROLE, -1)
                    item.setForeground(0, self._dir_color)
                    item.setFont(0, self._dir_font)
                else:
                    item.setText(1, format_size(size))
                    item.setData(1, SORT_ROLE, size)
                    item.setForeground(1, self._size_color)
                    item.setForeground(2, self._modified_color)
                    item.setForeground(3, self._perm_color)
                    total_size += size

                item.setText(2, mtime.strftime("%Y-%m-%d %H:%M"))
                item.setData(2, SORT_ROLE, mtime.timestamp())
                item.setText(3, perm_str)
                item.setData(3, SORT_ROLE, perm_str)

                items.append(item)

            items = self._sort_items(items)

            # Lazy loading: show first batch, queue the rest
            if len(items) > self._DISPLAY_BATCH_SIZE:
                visible = items[:self._DISPLAY_BATCH_SIZE]
                self._pending_items = items[self._DISPLAY_BATCH_SIZE:]
                self.file_tree.addTopLevelItems(visible)
                self._add_load_more_sentinel()
            else:
                self._pending_items = []
                self.file_tree.addTopLevelItems(items)

            self._total_size_bytes = total_size

            self.file_tree.blockSignals(False)
            self.file_tree.setUpdatesEnabled(True)
            self._update_status_bar()
            self.directory_changed.emit(self.current_path)

        except Exception as e:
            self.file_tree.blockSignals(False)
            self.file_tree.setUpdatesEnabled(True)
            logger.error(f"Error processing listing: {e}")

    # ── Lazy loading helpers ──

    _LOAD_MORE_SENTINEL = "__LOAD_MORE__"

    def _add_load_more_sentinel(self):
        """Add a 'Load more…' item to the bottom of the tree."""
        remaining = len(getattr(self, '_pending_items', []))
        item = QTreeWidgetItem()
        item.setText(0, f"  Load more ({remaining} remaining)…")
        item.setData(0, Qt.UserRole, self._LOAD_MORE_SENTINEL)
        item.setData(0, self.IS_DIR_ROLE, False)
        item.setForeground(0, QColor("#7dc4e4"))
        font = QFont()
        font.setItalic(True)
        item.setFont(0, font)
        self.file_tree.addTopLevelItem(item)

    def _load_more_items(self):
        """Load the next batch of pending items into the tree."""
        pending = getattr(self, '_pending_items', [])
        if not pending:
            return
        # Remove old sentinel
        root = self.file_tree.invisibleRootItem()
        for i in range(root.childCount() - 1, -1, -1):
            if root.child(i).data(0, Qt.UserRole) == self._LOAD_MORE_SENTINEL:
                root.takeChild(i)
                break

        batch = pending[:self._DISPLAY_BATCH_SIZE]
        self._pending_items = pending[self._DISPLAY_BATCH_SIZE:]

        self.file_tree.setUpdatesEnabled(False)
        for item in batch:
            self.file_tree.addTopLevelItem(item)
        if self._pending_items:
            self._add_load_more_sentinel()
        self.file_tree.setUpdatesEnabled(True)
        self._update_status_bar()

    def _on_home_ready(self, home_path: str):
        """Handle home directory result — navigate to it."""
        self.navigate_to(home_path)

    def _on_remote_op_done(self, operation: str, meta: dict):
        """Handle remote operation completion with targeted tree updates.

        Instead of re-listing the entire directory, we update only the
        affected tree items (delete → remove, rename → update, mkdir →
        insert).  Falls back to a full refresh for copy or if the
        targeted update fails.
        """
        logger.info(f"Remote operation '{operation}' completed successfully")
        if operation == 'delete':
            count = getattr(self, '_pending_delete_count', 0)
            if count > 1:
                self._pending_delete_count = count - 1
                self._show_busy(
                    f"Deleting... ({self._pending_delete_count} remaining)"
                )
                # Remove just this item from the tree immediately
                self._remove_tree_item(meta.get('path', ''))
                return  # Don't clear busy until all deletes are done
            self._pending_delete_count = 0

        self._clear_busy()

        # Try targeted update; fall back to full refresh on failure
        try:
            if operation == 'delete':
                self._remove_tree_item(meta.get('path', ''))
                self._update_status_bar()
            elif operation == 'rename':
                self._rename_tree_item(
                    meta.get('old_path', ''),
                    meta.get('new_path', ''),
                    meta.get('new_name', ''),
                )
            elif operation == 'mkdir':
                self._insert_dir_item(meta.get('name', ''), meta.get('path', ''))
                self._update_status_bar()
            else:
                # copy or unknown — full refresh
                self.refresh()
        except Exception as e:
            logger.debug(f"Delta update failed, doing full refresh: {e}")
            self.refresh()

    # ── Tree delta helpers ──

    def _find_tree_item(self, path: str) -> Optional[int]:
        """Return the top-level index of the item with the given path, or None."""
        root = self.file_tree.invisibleRootItem()
        for i in range(root.childCount()):
            if root.child(i).data(0, Qt.UserRole) == path:
                return i
        return None

    def _remove_tree_item(self, path: str):
        """Remove a single item from the tree by path."""
        idx = self._find_tree_item(path)
        if idx is not None:
            self.file_tree.takeTopLevelItem(idx)

    def _rename_tree_item(self, old_path: str, new_path: str, new_name: str):
        """Update an item's name and path in-place after a rename."""
        idx = self._find_tree_item(old_path)
        if idx is not None:
            item = self.file_tree.topLevelItem(idx)
            item.setText(0, new_name)
            item.setData(0, Qt.UserRole, new_path)
            is_dir = item.data(0, self.IS_DIR_ROLE)
            item.setData(0, self.SORT_ROLE,
                         ('0' if is_dir else '1') + new_name.lower())
        else:
            # Item not found — fall back to full refresh
            self.refresh()

    def _insert_dir_item(self, name: str, path: str):
        """Insert a new directory item into the tree at the right position."""
        item = QTreeWidgetItem()
        item.setIcon(0, self._get_file_icon(name, True))
        item.setText(0, name)
        item.setData(0, Qt.UserRole, path)
        item.setData(0, self.IS_DIR_ROLE, True)
        item.setData(0, self.SORT_ROLE, '0' + name.lower())
        item.setText(1, "—")
        item.setData(1, self.SORT_ROLE, -1)
        item.setForeground(0, self._dir_color)
        item.setFont(0, self._dir_font)
        item.setText(2, _time.strftime(
            "%Y-%m-%d %H:%M", _time.localtime(_time.time())))
        item.setData(2, self.SORT_ROLE, _time.time())
        item.setText(3, "755")
        item.setData(3, self.SORT_ROLE, "755")

        # Insert at correct sorted position among directories
        root = self.file_tree.invisibleRootItem()
        insert_at = 0
        name_lower = name.lower()
        for i in range(root.childCount()):
            child = root.child(i)
            if not child.data(0, self.IS_DIR_ROLE):
                break  # Past all directories
            if (child.data(0, self.SORT_ROLE) or '') <= '0' + name_lower:
                insert_at = i + 1
            else:
                break
        self.file_tree.insertTopLevelItem(insert_at, item)

    def _on_file_info_ready(self, metadata):
        """Handle file info result — show properties dialog."""
        try:
            info_text = (
                f"Name: {metadata.name}\n"
                f"Path: {metadata.path}\n"
                f"Size: {self._format_size(metadata.size)}\n"
                f"Modified: {metadata.modified}\n"
                f"Permissions: {oct(metadata.permissions)}\n"
                f"Type: {'Directory' if metadata.is_dir else 'File'}"
            )
            QMessageBox.information(self, "Properties", info_text)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_remote_op_error(self, error_msg: str):
        """Handle remote operation error."""
        logger.error(f"Remote operation error: {error_msg}")
        # Decrement pending delete count if active
        count = getattr(self, '_pending_delete_count', 0)
        if count > 0:
            self._pending_delete_count = max(count - 1, 0)
            if self._pending_delete_count == 0:
                self._clear_busy()
                self.refresh()
        else:
            self._clear_busy()
        QMessageBox.warning(self, "Remote Operation Failed", error_msg)

    def navigate_to(self, path: str):
        """Navigate to directory and refresh listing."""
        try:
            if self.is_remote:
                # For remote, use async listing — _on_listing_ready will update UI
                self._run_remote_op('list_dir', path=path)
                return
            else:
                # For local, verify it's a directory
                if os.path.isdir(path):
                    self.current_path = os.path.abspath(path)
                else:
                    QMessageBox.warning(
                        self,
                        "Invalid Path",
                        f"Directory does not exist: {path}"
                    )
                    return

            self.path_input.setText(self.current_path)
            self.refresh()
            self.directory_changed.emit(self.current_path)
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            QMessageBox.critical(self, "Navigation Error", str(e))

    # Maximum items to display before showing "Load more…"
    _DISPLAY_BATCH_SIZE = 500

    def refresh(self):
        """Refresh current directory listing."""
        if self.is_remote:
            # Use async worker for remote — _on_listing_ready handles UI update
            # Resolve home directory on first use
            if self.current_path in ('.', '', '~'):
                self._run_remote_op('home')
            else:
                self._run_remote_op('list_dir', path=self.current_path)
            return

        # Local: run scandir in a background thread
        # Cancel any in-flight local listing first
        if self._local_list_worker and self._local_list_worker.isRunning():
            self._local_list_worker.wait(500)

        self._pending_items = []
        path = self.current_path
        show_hidden = self.show_hidden

        worker = _LocalListWorker(path, show_hidden)
        worker.listing_ready.connect(self._on_local_listing_ready)
        worker.error.connect(lambda msg: QMessageBox.critical(self, "Refresh Error", msg))
        worker.start()
        self._local_list_worker = worker  # prevent GC

    def _on_local_listing_ready(self, path: str, entries: list):
        """Build tree items from pre-collected local metadata (main thread)."""
        try:
            self.current_path = path
            self.path_input.setText(path)

            self.file_tree.setUpdatesEnabled(False)
            self.file_tree.blockSignals(True)
            self.file_tree.clear()

            get_icon = self._get_file_icon
            format_size = self._format_size
            SORT_ROLE = self.SORT_ROLE
            IS_DIR_ROLE = self.IS_DIR_ROLE
            total_size = 0

            dir_items = []
            file_items = []

            for name, full_path, is_dir, size, mtime, perm_str, is_symlink in entries:
                item = QTreeWidgetItem()
                item.setIcon(0, get_icon(name, is_dir))
                display_name = f"{name} \u2192" if is_symlink else name
                item.setText(0, display_name)
                item.setData(0, Qt.UserRole, full_path)
                item.setData(0, IS_DIR_ROLE, is_dir)
                name_lower = name.lower()
                item.setData(0, SORT_ROLE, ('0' if is_dir else '1') + name_lower)

                if is_dir:
                    item.setText(1, "—")
                    item.setData(1, SORT_ROLE, -1)
                    item.setForeground(0, self._dir_color)
                    item.setFont(0, self._dir_font)
                else:
                    item.setText(1, format_size(size))
                    item.setData(1, SORT_ROLE, size)
                    item.setForeground(1, self._size_color)
                    item.setForeground(2, self._modified_color)
                    item.setForeground(3, self._perm_color)
                    total_size += size

                item.setText(2, _time.strftime(
                    "%Y-%m-%d %H:%M", _time.localtime(mtime)))
                item.setData(2, SORT_ROLE, mtime)
                item.setText(3, perm_str)
                item.setData(3, SORT_ROLE, perm_str)

                if is_dir:
                    dir_items.append((name_lower, item))
                else:
                    file_items.append((name_lower, item))

            # Default name sort (dirs first), then apply user's sort
            dir_items.sort(key=lambda x: x[0])
            file_items.sort(key=lambda x: x[0])
            all_items = [it for _, it in dir_items] + [it for _, it in file_items]
            all_items = self._sort_items(all_items)

            # Lazy loading: show first batch, queue the rest
            if len(all_items) > self._DISPLAY_BATCH_SIZE:
                visible = all_items[:self._DISPLAY_BATCH_SIZE]
                self._pending_items = all_items[self._DISPLAY_BATCH_SIZE:]
                self.file_tree.addTopLevelItems(visible)
                self._add_load_more_sentinel()
            else:
                self._pending_items = []
                self.file_tree.addTopLevelItems(all_items)

            self._total_size_bytes = total_size

            self.file_tree.blockSignals(False)
            self.file_tree.setUpdatesEnabled(True)
            self._update_status_bar()
            self._apply_filter()
        except Exception as e:
            self.file_tree.blockSignals(False)
            self.file_tree.setUpdatesEnabled(True)
            logger.error(f"Refresh failed: {e}")
            QMessageBox.critical(self, "Refresh Error", str(e))

    def get_selected_paths(self) -> List[str]:
        """Get paths of selected items."""
        paths = []
        for item in self.file_tree.selectedItems():
            path = item.data(0, Qt.UserRole)
            if path and path != self._LOAD_MORE_SENTINEL:
                paths.append(path)
        return paths

    # Extension → (text color, bg color) for known file types
    _EXT_COLORS = {
        # GROMACS input — bright cyan on dark teal
        '.mdp': ('#7dc4e4', '#1a3a4f'),
        '.gro': ('#7dc4e4', '#1a3a4f'),
        '.top': ('#7dc4e4', '#1a3a4f'),
        '.tpr': ('#7dc4e4', '#1a3a4f'),
        '.itp': ('#7dc4e4', '#1a3a4f'),
        '.ndx': ('#7dc4e4', '#1a3a4f'),
        # GROMACS output — bright green on dark green
        '.xtc': ('#a6da95', '#1a3a28'),
        '.edr': ('#a6da95', '#1a3a28'),
        '.trr': ('#a6da95', '#1a3a28'),
        '.cpt': ('#a6da95', '#1a3a28'),
        '.xvg': ('#a6da95', '#1a3a28'),
        '.log': ('#eed49f', '#3a3520'),
        # Scripts / config — bright orange on dark brown
        '.sh':  ('#f5a97f', '#3a2820'),
        '.py':  ('#f5a97f', '#3a2820'),
        '.slurm': ('#f5a97f', '#3a2820'),
        '.sbatch': ('#f5a97f', '#3a2820'),
        # Data / text — bright white on slate
        '.dat': ('#cad3f5', '#2e3148'),
        '.txt': ('#cad3f5', '#2e3148'),
        '.csv': ('#cad3f5', '#2e3148'),
        '.json': ('#cad3f5', '#2e3148'),
        # Structure files — bright purple on dark purple
        '.pdb': ('#c6a0f6', '#2e2048'),
        '.xyz': ('#c6a0f6', '#2e2048'),
        # Common extras
        '.pdf': ('#ed8796', '#3a2028'),
        '.ff':  ('#8aadf4', '#1e2a4a'),
    }

    def _get_file_icon(self, filename: str, is_dir: bool) -> QIcon:
        """Get appropriate icon (cached) for file/directory.

        Directories use the system folder icon.
        Files show a small badge with the extension text (e.g. 'mdp', 'sh').
        """
        if is_dir:
            key = '__dir__'
        else:
            ext = os.path.splitext(filename)[1].lower()
            key = ext if ext else '__file__'

        if key not in self._icon_cache:
            if key == '__dir__':
                style = QApplication.style()
                self._icon_cache[key] = style.standardIcon(style.SP_DirIcon)
            elif key == '__file__':
                style = QApplication.style()
                self._icon_cache[key] = style.standardIcon(style.SP_FileIcon)
            else:
                self._icon_cache[key] = self._make_ext_icon(key)

        return self._icon_cache[key]

    def _make_ext_icon(self, ext: str) -> QIcon:
        """Render a visible icon with the extension text as a badge."""
        label = ext.lstrip('.').upper()
        if len(label) > 4:
            label = label[:4]

        fg_hex, bg_hex = self._EXT_COLORS.get(ext, ('#cad3f5', '#363a4f'))
        fg = QColor(fg_hex)
        bg = QColor(bg_hex)

        # Scale factor for HiDPI
        scale = 2
        w = max(36, 10 + len(label) * 9) * scale
        h = 22 * scale
        px = QPixmap(w, h)
        px.setDevicePixelRatio(scale)
        px.fill(QColor(0, 0, 0, 0))  # transparent

        logical_w = w // scale
        logical_h = h // scale

        p = QPainter(px)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(1, 1, logical_w - 2, logical_h - 2, 4, 4)

        # Border for contrast
        border_color = QColor(fg_hex)
        border_color.setAlpha(80)
        p.setPen(border_color)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(1, 1, logical_w - 2, logical_h - 2, 4, 4)

        p.setPen(fg)
        font = QFont("Menlo", 9, QFont.Bold)
        font.setStyleStrategy(QFont.PreferAntialias)
        p.setFont(font)
        p.drawText(0, 0, logical_w, logical_h, Qt.AlignCenter, label)
        p.end()

        return QIcon(px)

    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to human-readable size."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"

    def _update_status_bar(self):
        """Update status bar with item count and tracked total size."""
        item_count = self.file_tree.topLevelItemCount()
        self.status_label.setText(
            f"{item_count} items | Total: {self._format_size(self._total_size_bytes)}"
        )
        self.status_label.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 13px;")

    def _show_busy(self, message: str):
        """Show a busy/progress message in the status bar."""
        self.status_label.setText(f"⏳  {message}")
        self.status_label.setStyleSheet(
            "color: #f5a623; font-size: 13px; font-weight: bold;"
        )
        # Force immediate repaint so the message is visible before blocking ops
        self.status_label.repaint()

    def _clear_busy(self):
        """Clear the busy message and restore normal status bar."""
        self._update_status_bar()

    def _sort_items(self, items: list) -> list:
        """Sort a list of QTreeWidgetItems using the current sort settings.

        Called after populating items from a refresh so the user's chosen
        sort column and order are preserved across refreshes.
        """
        if not items or (self._sort_column == 0 and self._sort_order == Qt.AscendingOrder):
            return items  # Default order — already sorted by name
        col = self._sort_column
        role = self.SORT_ROLE
        reverse = self._sort_order == Qt.DescendingOrder
        items.sort(key=lambda it: it.data(col, role) or "", reverse=reverse)
        return items

    def _on_header_clicked(self, logical_index: int):
        """Sort file list when a column header is clicked."""
        if logical_index == self._sort_column:
            self._sort_order = (Qt.DescendingOrder if self._sort_order == Qt.AscendingOrder
                                else Qt.AscendingOrder)
        else:
            self._sort_column = logical_index
            self._sort_order = Qt.AscendingOrder

        self.file_tree.header().setSortIndicator(
            self._sort_column, self._sort_order
        )

        # Collect sort keys + indices, then reorder
        # (avoids O(n²) takeChild(0) pattern)
        root = self.file_tree.invisibleRootItem()
        count = root.childCount()
        if count < 2 and not self._pending_items:
            return

        self.file_tree.setUpdatesEnabled(False)

        # Extract all visible items (take from end to avoid shifting)
        items = []
        for i in range(count - 1, -1, -1):
            child = root.takeChild(i)
            # Skip the "Load more…" sentinel
            if child.data(0, Qt.UserRole) == self._LOAD_MORE_SENTINEL:
                continue
            items.append(child)
        items.reverse()

        # Merge in any pending (lazy-loaded) items so the full list is sorted
        if self._pending_items:
            items.extend(self._pending_items)
            self._pending_items = []

        # Sort
        reverse = self._sort_order == Qt.DescendingOrder
        col = self._sort_column
        role = self.SORT_ROLE
        items.sort(key=lambda it: it.data(col, role) or "", reverse=reverse)

        # Re-add with lazy loading if needed
        if len(items) > self._DISPLAY_BATCH_SIZE:
            visible = items[:self._DISPLAY_BATCH_SIZE]
            self._pending_items = items[self._DISPLAY_BATCH_SIZE:]
            for item in visible:
                root.addChild(item)
            self._add_load_more_sentinel()
        else:
            for item in items:
                root.addChild(item)

        self.file_tree.setUpdatesEnabled(True)

    def _start_drag(self, supported_actions):
        """Create QDrag with selected file paths."""
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            return

        mime_data = QMimeData()

        # Add custom mime type with JSON data
        transfer_data = {
            'paths': selected_paths,
            'is_remote': self.is_remote,
            'source_title': self.title
        }
        mime_data.setData(
            TRANSFPRO_FILES_MIME_TYPE,
            json.dumps(transfer_data).encode('utf-8')
        )

        # Also add file URLs for external drag-drop
        if not self.is_remote:
            urls = [QUrl.fromLocalFile(path) for path in selected_paths]
            mime_data.setUrls(urls)

        drag = QDrag(self.file_tree)
        drag.setMimeData(mime_data)

        # Set drag pixmap
        pixmap = QPixmap(100, 50)
        pixmap.fill(QColor(200, 200, 200))
        drag.setPixmap(pixmap)

        drag.exec_(supported_actions)

    # ── Event filter for tree-viewport drag/drop ──

    def eventFilter(self, obj, event):
        """Intercept drag/drop events on the tree viewport and handle them here.

        QAbstractItemView routes drag events through the viewport widget,
        so a viewport event filter is the reliable way to override them.
        """
        etype = event.type()
        if obj is self.file_tree.viewport():
            if etype == QEvent.DragEnter:
                self.dragEnterEvent(event)
                return True
            elif etype == QEvent.DragMove:
                self.dragMoveEvent(event)
                return True
            elif etype == QEvent.DragLeave:
                self.dragLeaveEvent(event)
                return True
            elif etype == QEvent.Drop:
                self.dropEvent(event)
                return True
        return super().eventFilter(obj, event)

    def dragEnterEvent(self, event):
        """Handle drag enter event — show drop zone overlay."""
        mime_data = event.mimeData()
        if (mime_data.hasFormat(TRANSFPRO_FILES_MIME_TYPE) or
                mime_data.hasUrls()):
            event.acceptProposedAction()
            # Determine direction from source data
            is_upload = self.is_remote
            if mime_data.hasFormat(TRANSFPRO_FILES_MIME_TYPE):
                try:
                    raw = mime_data.data(TRANSFPRO_FILES_MIME_TYPE)
                    data = json.loads(bytes(raw).decode('utf-8'))
                    source_is_remote = data.get('is_remote', False)
                    is_upload = (not source_is_remote and self.is_remote)
                except Exception:
                    pass
            self._drop_overlay.set_upload(is_upload)
            # Overlay is a child of file_tree — use the viewport geometry
            # so it covers the scrollable area below the header row
            self._drop_overlay.setGeometry(self.file_tree.viewport().geometry())
            self._drop_overlay.raise_()
            self._drop_overlay.show()

    def dragLeaveEvent(self, event):
        """Hide drop zone overlay when drag leaves."""
        self._drop_overlay.hide()

    def dragMoveEvent(self, event):
        """Handle drag move event — accept drops on directories or empty space."""
        event.acceptProposedAction()

    def dropEvent(self, event):
        """Handle drop event to trigger transfer."""
        self._drop_overlay.hide()
        mime_data = event.mimeData()

        # Get target directory
        # event.pos() is in viewport coordinates (from the event filter),
        # which is what itemAt() expects
        item = self.file_tree.itemAt(event.pos())
        target_dir = self.current_path
        if item:
            path = item.data(0, Qt.UserRole)
            if path and item.data(0, self.IS_DIR_ROLE):
                target_dir = path

        # Parse source files from custom mime data
        if mime_data.hasFormat(TRANSFPRO_FILES_MIME_TYPE):
            try:
                raw = mime_data.data(TRANSFPRO_FILES_MIME_TYPE)
                data = json.loads(bytes(raw).decode('utf-8'))
                source_paths = data.get('paths', [])
                source_is_remote = data.get('is_remote', False)

                # Determine transfer direction based on source, not drop target
                if source_is_remote and not self.is_remote:
                    # Remote → Local = Download
                    self.transfer_download_requested.emit(source_paths, target_dir)
                elif not source_is_remote and self.is_remote:
                    # Local → Remote = Upload
                    self.transfer_upload_requested.emit(source_paths, target_dir)

                event.acceptProposedAction()
            except Exception as e:
                logger.error(f"Drop processing failed: {e}")
                event.ignore()
        elif mime_data.hasUrls():
            # Handle URL drops from external apps (e.g. macOS Finder)
            raw_paths = [url.toLocalFile() for url in mime_data.urls()]
            local_paths = [p.rstrip('/') for p in raw_paths if p]
            logger.info(
                f"External drop: {len(local_paths)} local paths → {target_dir}"
            )
            for p in local_paths:
                logger.info(f"  ext-drop path: {p}  isdir={os.path.isdir(p)}")

            if local_paths:
                if self.is_remote:
                    # External (local) → Remote = upload
                    self.transfer_upload_requested.emit(local_paths, target_dir)
                else:
                    # External (local) → Local = local file copy
                    import shutil
                    for src in local_paths:
                        dst = os.path.join(target_dir, os.path.basename(src))
                        if os.path.abspath(src) == os.path.abspath(dst):
                            continue
                        try:
                            if os.path.isdir(src):
                                shutil.copytree(src, dst)
                            else:
                                shutil.copy2(src, dst)
                        except Exception as e:
                            logger.error(f"Local copy from external drop: {e}")
                    self.refresh()
                event.acceptProposedAction()
            else:
                event.ignore()
        else:
            event.ignore()

    def _on_path_entered(self):
        """Handle path input Enter key."""
        path = self.path_input.text().strip()
        if path:
            self.navigate_to(path)

    def _on_up_clicked(self):
        """Handle up button click."""
        if self.is_remote:
            path = self.current_path.rstrip('/')
            parent = path.rsplit('/', 1)[0] or '/'
        else:
            parent = os.path.dirname(self.current_path)

        if parent and parent != self.current_path:
            self.navigate_to(parent)

    def _on_home_clicked(self):
        """Handle home button click."""
        if self.is_remote and self.sftp_manager:
            ssh = getattr(self.sftp_manager, 'ssh', None)
            if ssh and hasattr(ssh, 'is_connected') and not ssh.is_connected():
                logger.debug("Home click skipped — not connected")
                return
            # Async: _on_home_ready will call navigate_to
            self._run_remote_op('home')
        else:
            home = os.path.expanduser("~")
            self.navigate_to(home)

    def _on_show_hidden_changed(self, state):
        """Handle show hidden toggle."""
        self.show_hidden = state == Qt.Checked
        self.refresh()

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle double-click: navigate into directory, or open file.

        For remote symlinks whose target type is unknown (is_dir=False but
        is_symlink=True), we optimistically try to navigate into them.
        If the SFTP listing succeeds the symlink pointed to a directory;
        if it fails the error handler will show a message.
        """
        path = item.data(0, Qt.UserRole)
        if not path:
            return

        # "Load more…" sentinel
        if path == self._LOAD_MORE_SENTINEL:
            self._load_more_items()
            return

        is_dir = item.data(0, self.IS_DIR_ROLE)

        if is_dir:
            self.navigate_to(path)
        elif self.is_remote:
            # Check if this is a symlink — it might point to a directory.
            display_text = item.text(0)
            is_symlink = display_text.endswith(" \u2192")
            if is_symlink:
                # Try to navigate; _on_remote_op_error handles failure
                self.navigate_to(path)
            else:
                # Regular remote file: emit signal so parent can download & open
                self.open_remote_file_requested.emit(path)
        else:
            # Local file: open directly with system default app
            self._open_local_file(path)

    def _open_local_file(self, path: str):
        """Open a local file with the system default application."""
        try:
            import sys
            if sys.platform == 'darwin':
                subprocess.Popen(['open', path])
            elif sys.platform.startswith('linux'):
                subprocess.Popen(['xdg-open', path])
            else:
                os.startfile(path)
        except Exception as e:
            logger.error(f"Failed to open file: {e}")
            QMessageBox.warning(self, "Open Error", f"Could not open file: {e}")

    def _on_selection_changed(self):
        """Handle selection change."""
        paths = self.get_selected_paths()
        self.files_selected.emit(paths)

    def _on_context_menu(self, position):
        """Handle right-click context menu."""
        item = self.file_tree.itemAt(position)
        menu = QMenu(self)

        # Snapshot selection BEFORE the context menu opens, so right-click
        # doesn't cause stale references from click-triggered deselection.
        selected_items = list(self.file_tree.selectedItems())
        multi = len(selected_items) > 1

        if item:
            item_path = item.data(0, Qt.UserRole)
            is_dir = item.data(0, self.IS_DIR_ROLE)

            # Open / Open With — only for files, not directories
            if not is_dir and not multi:
                open_action = menu.addAction("Open")
                open_action.triggered.connect(
                    lambda: self._open_file(item_path)
                )
                open_with_action = menu.addAction("Open With...")
                open_with_action.triggered.connect(
                    lambda: self._open_file_with(item_path)
                )
                menu.addSeparator()

            # New Folder
            new_folder_action = menu.addAction("New Folder")
            new_folder_action.triggered.connect(self._on_new_folder)

            # Rename — disabled when multiple items selected
            rename_action = menu.addAction("Rename")
            rename_action.triggered.connect(
                lambda: self._on_rename(item, item_path)
            )
            if multi:
                rename_action.setEnabled(False)

            # Delete — always operate on ALL selected items
            if multi:
                frozen = list(selected_items)          # freeze for lambda
                delete_action = menu.addAction(f"Delete ({len(frozen)} items)")
                delete_action.triggered.connect(
                    lambda: self._on_delete_multiple(frozen)
                )
            else:
                delete_action = menu.addAction("Delete")
                delete_action.triggered.connect(
                    lambda: self._on_delete(item_path, is_dir)
                )

            menu.addSeparator()

            # Copy Path
            copy_path_action = menu.addAction("Copy Path")
            copy_path_action.triggered.connect(
                lambda: self._on_copy_path(item_path)
            )

            # Properties
            properties_action = menu.addAction("Properties")
            properties_action.triggered.connect(
                lambda: self._on_properties(item_path)
            )
        else:
            # Right-click on empty area
            new_folder_action = menu.addAction("New Folder")
            new_folder_action.triggered.connect(self._on_new_folder)

        menu.addSeparator()

        # Copy / Paste
        copy_files_action = menu.addAction('Copy  (Ctrl+C)')
        copy_files_action.triggered.connect(self._on_copy_files)
        if not selected_items:
            copy_files_action.setEnabled(False)

        paste_files_action = menu.addAction('Paste  (Ctrl+V)')
        paste_files_action.triggered.connect(self._on_paste_files)
        if not _file_clipboard.get('paths'):
            paste_files_action.setEnabled(False)

        menu.addSeparator()

        # Refresh
        refresh_action = menu.addAction("Refresh")
        refresh_action.triggered.connect(self.refresh)

        menu.exec_(self.file_tree.mapToGlobal(position))

    def _on_new_folder(self):
        """Handle new folder creation."""
        name, ok = QInputDialog.getText(
            self,
            "New Folder",
            "Folder name:",
            text="New Folder"
        )
        if ok and name:
            try:
                if self.is_remote:
                    path = f"{self.current_path.rstrip('/')}/{name}"
                    # Async: _on_remote_op_done will refresh
                    self._run_remote_op('mkdir', path=path)
                else:
                    path = os.path.join(self.current_path, name)
                    os.makedirs(path, exist_ok=True)
                    self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _on_rename(self, item: QTreeWidgetItem, path: str):
        """Handle file/directory rename."""
        name, ok = QInputDialog.getText(
            self,
            "Rename",
            "New name:",
            text=item.text(0)
        )
        if ok and name:
            try:
                if self.is_remote:
                    new_path = f"{self.current_path.rstrip('/')}/{name}"
                    # Async: _on_remote_op_done will refresh
                    self._run_remote_op('rename', old_path=path, new_path=new_path)
                else:
                    new_path = os.path.join(self.current_path, name)
                    os.rename(path, new_path)
                    self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _on_delete(self, path: str, is_dir: bool):
        """Handle file/directory deletion."""
        reply = QMessageBox.warning(
            self,
            "Confirm Delete",
            f"Delete {os.path.basename(path)}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            name = os.path.basename(path)
            self._show_busy(f"Deleting {name}...")
            try:
                if self.is_remote:
                    self._pending_delete_count = 1
                    self._run_remote_op('delete', path=path, is_dir=is_dir)
                else:
                    if is_dir:
                        import shutil
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                    self._clear_busy()
                    self.refresh()
            except Exception as e:
                self._clear_busy()
                QMessageBox.critical(self, "Error", str(e))

    def _on_delete_multiple(self, items: list):
        """Handle deletion of multiple selected files/directories."""
        names = []
        for item in items:
            path = item.data(0, Qt.UserRole)
            if path:
                name = path.split('/')[-1] if '/' in path else os.path.basename(path)
                names.append(name)

        if not names:
            return

        # Show first few names in confirmation
        display = ", ".join(names[:5])
        if len(names) > 5:
            display += f" ... (+{len(names) - 5} more)"

        reply = QMessageBox.warning(
            self,
            "Confirm Delete",
            f"Delete {len(names)} items?\n\n{display}",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._show_busy(f"Deleting {len(names)} items...")
            try:
                delete_count = 0
                for item in items:
                    path = item.data(0, Qt.UserRole)
                    is_dir = item.data(0, self.IS_DIR_ROLE)
                    if not path:
                        continue
                    if self.is_remote:
                        self._run_remote_op('delete', path=path, is_dir=is_dir)
                        delete_count += 1
                    else:
                        if is_dir:
                            import shutil
                            shutil.rmtree(path)
                        else:
                            os.remove(path)
                if self.is_remote:
                    # Track how many remote deletes are pending
                    self._pending_delete_count = delete_count
                else:
                    self._clear_busy()
                    self.refresh()
            except Exception as e:
                self._clear_busy()
                QMessageBox.critical(self, "Error", str(e))

    def _open_file(self, path: str):
        """Open a file with the system default application."""
        import sys
        if self.is_remote:
            # For remote files, emit signal to download & open
            self.open_remote_file_requested.emit(path)
        else:
            try:
                if sys.platform == 'darwin':
                    subprocess.Popen(['open', path])
                elif sys.platform.startswith('linux'):
                    subprocess.Popen(['xdg-open', path])
                else:
                    os.startfile(path)
            except Exception as e:
                logger.error(f"Failed to open file: {e}")
                QMessageBox.warning(self, "Open Error", f"Could not open file: {e}")

    def _open_file_with(self, path: str):
        """Open a file with a user-chosen application."""
        import sys
        if sys.platform == 'darwin':
            self._open_with_macos(path)
        elif sys.platform.startswith('linux'):
            self._open_with_linux(path)
        else:
            self._open_file(path)  # Fallback to default on other platforms

    def _open_with_macos(self, path: str):
        """Show macOS 'Open With' dialog using native chooser."""
        if self.is_remote:
            # For remote: need to download first, then open with chosen app
            # We'll use a file dialog to pick the app, store it, then download
            app_path, _ = QFileDialog.getOpenFileName(
                self, "Select Application",
                "/Applications",
                "Applications (*.app);;All Files (*)"
            )
            if app_path:
                self.open_remote_with_requested.emit(path, app_path)
        else:
            # Use native macOS "open -a" chooser or let user pick
            app_path, _ = QFileDialog.getOpenFileName(
                self, "Select Application",
                "/Applications",
                "Applications (*.app);;All Files (*)"
            )
            if app_path:
                try:
                    subprocess.Popen(['open', '-a', app_path, path])
                except Exception as e:
                    logger.error(f"Failed to open with app: {e}")
                    QMessageBox.warning(self, "Open Error", f"Could not open file: {e}")

    def _open_with_linux(self, path: str):
        """Show Linux application chooser."""
        app_cmd, ok = QInputDialog.getText(
            self, "Open With",
            "Enter application command (e.g., gedit, code, vim):"
        )
        if ok and app_cmd:
            if self.is_remote:
                self.open_remote_with_requested.emit(path, app_cmd)
            else:
                try:
                    subprocess.Popen([app_cmd, path])
                except Exception as e:
                    logger.error(f"Failed to open with {app_cmd}: {e}")
                    QMessageBox.warning(self, "Open Error", f"Could not open file: {e}")

    def _on_copy_path(self, path: str):
        """Handle copy path to clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(path)
        logger.info(f"Copied to clipboard: {path}")

    def _on_properties(self, path: str):
        """Handle properties dialog."""
        try:
            if self.is_remote:
                # Async: _on_file_info_ready will show dialog
                self._run_remote_op('info', path=path)
            else:
                stat = os.stat(path)
                is_dir = os.path.isdir(path)
                info_text = (
                    f"Name: {os.path.basename(path)}\n"
                    f"Path: {path}\n"
                    f"Size: {self._format_size(stat.st_size) if not is_dir else '—'}\n"
                    f"Modified: {datetime.fromtimestamp(stat.st_mtime)}\n"
                    f"Permissions: {oct(stat.st_mode)[-3:]}\n"
                    f"Type: {'Directory' if is_dir else 'File'}"
                )
                QMessageBox.information(self, "Properties", info_text)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


    # ── Copy / Paste ──

    def _on_copy_files(self):
        """Copy selected file paths to internal clipboard."""
        paths = self.get_selected_paths()
        if paths:
            _file_clipboard['paths'] = list(paths)
            _file_clipboard['is_remote'] = self.is_remote
            logger.info(f"Copied {len(paths)} file(s) to clipboard")

    def _on_paste_files(self):
        """Paste (transfer) files from clipboard to this pane's current directory."""
        paths = _file_clipboard.get('paths', [])
        source_remote = _file_clipboard.get('is_remote', False)
        if not paths:
            return

        target_dir = self.current_path

        if source_remote and not self.is_remote:
            # Remote → Local = download
            self.transfer_download_requested.emit(paths, target_dir)
        elif not source_remote and self.is_remote:
            # Local → Remote = upload
            self.transfer_upload_requested.emit(paths, target_dir)
        elif source_remote and self.is_remote:
            # Remote → Remote = server-side copy via SSH cp -r
            self._show_busy(f"Copying {len(paths)} item(s)...")
            self._run_remote_op(
                'copy', src_paths=paths, dest_dir=target_dir
            )
        else:
            # Local → Local = local file copy
            import shutil
            for src in paths:
                dst = os.path.join(target_dir, os.path.basename(src))
                if src == dst:
                    continue
                try:
                    if os.path.isdir(src):
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
                except Exception as e:
                    logger.error(f"Local copy failed: {e}")
            self.refresh()

    # ── File Filter ──

    def _on_filter_changed(self, text: str):
        """Filter the visible file tree items by name pattern."""
        self._filter_text = text.strip().lower()
        self._apply_filter()

    def _apply_filter(self):
        """Show/hide tree items based on current filter text."""
        pattern = self._filter_text
        for i in range(self.file_tree.topLevelItemCount()):
            item = self.file_tree.topLevelItem(i)
            if not pattern:
                item.setHidden(False)
                continue
            name = item.text(0).lower()
            # Support fnmatch-style patterns (*.tpr) or plain substring
            if '*' in pattern or '?' in pattern:
                item.setHidden(not fnmatch.fnmatch(name, pattern))
            else:
                item.setHidden(pattern not in name)

    # ── Bookmark Methods ──

    def _load_bookmarks(self):
        """Load bookmarks from QSettings."""
        key = f"bookmarks_{'remote' if self.is_remote else 'local'}"
        settings = QSettings("TransfPro", "TransfPro")
        count = settings.beginReadArray(key)
        self._bookmarks = []
        for i in range(count):
            settings.setArrayIndex(i)
            name = settings.value("name", "")
            path = settings.value("path", "")
            if name and path:
                self._bookmarks.append((name, path))
        settings.endArray()

    def _save_bookmarks(self):
        """Save bookmarks to QSettings."""
        key = f"bookmarks_{'remote' if self.is_remote else 'local'}"
        settings = QSettings("TransfPro", "TransfPro")
        settings.beginWriteArray(key, len(self._bookmarks))
        for i, (name, path) in enumerate(self._bookmarks):
            settings.setArrayIndex(i)
            settings.setValue("name", name)
            settings.setValue("path", path)
        settings.endArray()

    def _rebuild_bookmark_buttons(self):
        """Rebuild bookmark buttons from current list."""
        layout = self._bookmark_bar_layout
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        bm_btn_qss = """
            QPushButton {
                background: rgba(245, 194, 66, 0.10);
                border: 1px solid rgba(245, 194, 66, 0.20);
                border-radius: 4px;
                color: #f5c242;
                padding: 1px 8px;
                font-size: 10px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(245, 194, 66, 0.25);
                border-color: rgba(245, 194, 66, 0.5);
                color: white;
            }
        """

        label = QLabel("⭐")
        label.setStyleSheet("font-size: 12px;")
        layout.addWidget(label)

        for idx, (name, path) in enumerate(self._bookmarks):
            btn = QPushButton(name)
            btn.setMaximumHeight(22)
            btn.setToolTip(f"Go to: {path}\nRight-click to remove")
            btn.setStyleSheet(bm_btn_qss)
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.clicked.connect(lambda checked, p=path: self.navigate_to(p))
            btn.customContextMenuRequested.connect(
                lambda pos, i=idx, b=btn: self._show_bookmark_menu(pos, i, b)
            )
            layout.addWidget(btn)

        # Add bookmark button
        add_btn = QPushButton("+ Bookmark")
        add_btn.setMaximumHeight(22)
        add_btn.setToolTip("Bookmark current directory")
        add_btn.setStyleSheet("""
            QPushButton {
                background: rgba(110, 115, 141, 0.15);
                border: 1px dashed rgba(110, 115, 141, 0.4);
                border-radius: 4px;
                color: #6e738d;
                padding: 1px 6px;
                font-size: 10px;
            }
            QPushButton:hover {
                background: rgba(110, 115, 141, 0.25);
                color: #cad3f5;
            }
        """)
        add_btn.clicked.connect(self._add_bookmark)
        layout.addWidget(add_btn)

        layout.addStretch()

    def _add_bookmark(self):
        """Bookmark the current directory."""
        path = self.current_path
        # Check for duplicates
        for name, bm_path in self._bookmarks:
            if bm_path == path:
                QMessageBox.information(self, "Already Bookmarked",
                                        f"This directory is already bookmarked as \"{name}\".")
                return

        # Use last segment as default name
        if self.is_remote:
            default_name = path.rstrip('/').rsplit('/', 1)[-1] or '/'
        else:
            default_name = os.path.basename(path) or path

        name, ok = QInputDialog.getText(
            self, "Add Bookmark", "Bookmark name:", text=default_name
        )
        if ok and name:
            self._bookmarks.append((name, path))
            self._save_bookmarks()
            self._rebuild_bookmark_buttons()

    def _show_bookmark_menu(self, pos, index: int, btn: QPushButton):
        """Show context menu for bookmark button."""
        menu = QMenu(self)
        remove_action = menu.addAction("Remove Bookmark")
        action = menu.exec_(btn.mapToGlobal(pos))
        if action == remove_action:
            if 0 <= index < len(self._bookmarks):
                self._bookmarks.pop(index)
                self._save_bookmarks()
                self._rebuild_bookmark_buttons()

    # ── Quick Transfer Macros ──────────────────────────────────────────

    def _load_transfer_macros(self):
        """Load transfer macros from QSettings."""
        settings = QSettings("TransfPro", "TransfPro")
        count = settings.beginReadArray("transfer_macros")
        self._transfer_macros = []
        for i in range(count):
            settings.setArrayIndex(i)
            name = settings.value("name", "")
            local_path = settings.value("local_path", "")
            remote_path = settings.value("remote_path", "")
            direction = settings.value("direction", "upload")
            if name and local_path and remote_path:
                self._transfer_macros.append({
                    'name': name,
                    'local_path': local_path,
                    'remote_path': remote_path,
                    'direction': direction,
                })
        settings.endArray()

    def _save_transfer_macros(self):
        """Save transfer macros to QSettings."""
        settings = QSettings("TransfPro", "TransfPro")
        settings.beginWriteArray("transfer_macros", len(self._transfer_macros))
        for i, macro in enumerate(self._transfer_macros):
            settings.setArrayIndex(i)
            settings.setValue("name", macro['name'])
            settings.setValue("local_path", macro['local_path'])
            settings.setValue("remote_path", macro['remote_path'])
            settings.setValue("direction", macro['direction'])
        settings.endArray()

    def _rebuild_macro_buttons(self):
        """Rebuild macro buttons from current list."""
        layout = self._macro_bar_layout
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        macro_btn_qss = """
            QPushButton {
                background: rgba(14, 165, 233, 0.1);
                color: #7dc4e4;
                border: 1px solid rgba(14, 165, 233, 0.15);
                border-radius: 3px;
                padding: 1px 6px;
                font-size: 10px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(14, 165, 233, 0.25);
                color: #91d7e3;
            }
            QPushButton:pressed {
                background: rgba(14, 165, 233, 0.05);
            }
        """

        label = QLabel("⚡")
        label.setStyleSheet("font-size: 12px;")
        layout.addWidget(label)

        for idx, macro in enumerate(self._transfer_macros):
            arrow = "⬆" if macro['direction'] == 'upload' else "⬇"
            btn = QPushButton(f"{arrow} {macro['name']}")
            btn.setMaximumHeight(22)
            if macro['direction'] == 'upload':
                tip = f"Upload: {macro['local_path']} → {macro['remote_path']}"
            else:
                tip = f"Download: {macro['remote_path']} → {macro['local_path']}"
            btn.setToolTip(f"{tip}\nRight-click to edit/remove")
            btn.setStyleSheet(macro_btn_qss)
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.clicked.connect(
                lambda checked, m=macro: self._run_transfer_macro(m)
            )
            btn.customContextMenuRequested.connect(
                lambda pos, i=idx, b=btn: self._show_macro_menu(pos, i, b)
            )
            layout.addWidget(btn)

        # Add macro button
        add_btn = QPushButton("+ Macro")
        add_btn.setMaximumHeight(22)
        add_btn.setToolTip("Add a quick transfer macro")
        add_btn.setStyleSheet("""
            QPushButton {
                background: rgba(166, 218, 149, 0.08);
                color: rgba(166, 218, 149, 0.6);
                border: 1px solid rgba(166, 218, 149, 0.12);
                border-radius: 3px;
                padding: 1px 4px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(166, 218, 149, 0.2);
                color: #a6da95;
            }
        """)
        add_btn.clicked.connect(self._add_transfer_macro)
        layout.addWidget(add_btn)

        layout.addStretch()

    def _run_transfer_macro(self, macro: dict):
        """Execute a transfer macro by emitting the signal."""
        self.transfer_macro_requested.emit(
            macro['local_path'], macro['remote_path'], macro['direction']
        )

    def _add_transfer_macro(self):
        """Add a new transfer macro using current paths as defaults."""
        result = self._macro_dialog()
        if result:
            self._transfer_macros.append(result)
            self._save_transfer_macros()
            self._rebuild_macro_buttons()

    def _edit_transfer_macro(self, index: int):
        """Edit an existing transfer macro."""
        if 0 <= index < len(self._transfer_macros):
            macro = self._transfer_macros[index]
            result = self._macro_dialog(macro)
            if result:
                self._transfer_macros[index] = result
                self._save_transfer_macros()
                self._rebuild_macro_buttons()

    def _show_macro_menu(self, pos, index: int, btn: QPushButton):
        """Show context menu for macro button."""
        menu = QMenu(self)
        edit_action = menu.addAction("Edit Macro")
        remove_action = menu.addAction("Remove Macro")
        action = menu.exec_(btn.mapToGlobal(pos))
        if action == edit_action:
            self._edit_transfer_macro(index)
        elif action == remove_action:
            if 0 <= index < len(self._transfer_macros):
                self._transfer_macros.pop(index)
                self._save_transfer_macros()
                self._rebuild_macro_buttons()

    def _macro_dialog(self, existing: dict = None):
        """Show a dialog for creating/editing a transfer macro.

        Returns a dict {name, local_path, remote_path, direction} or None.
        """
        from PyQt5.QtWidgets import QDialog, QFormLayout, QDialogButtonBox

        dlg = QDialog(self)
        dlg.setWindowTitle("Edit Transfer Macro" if existing else "Add Transfer Macro")
        dlg.setMinimumWidth(450)
        dlg.setStyleSheet("""
            QDialog {
                background: #1e2030;
                color: #cad3f5;
            }
            QLabel {
                color: #cad3f5;
                font-size: 12px;
            }
            QLineEdit {
                background: #24273a;
                color: #cad3f5;
                border: 1px solid #363a4f;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QComboBox {
                background: #24273a;
                color: #cad3f5;
                border: 1px solid #363a4f;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QPushButton {
                background: #363a4f;
                color: #cad3f5;
                border: 1px solid #494d64;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #494d64;
            }
        """)

        form = QFormLayout(dlg)
        form.setSpacing(10)
        form.setContentsMargins(16, 16, 16, 16)

        name_edit = QLineEdit()
        name_edit.setPlaceholderText("e.g. Sync configs")
        if existing:
            name_edit.setText(existing['name'])

        local_edit = QLineEdit()
        local_edit.setPlaceholderText("/home/user/data")
        if existing:
            local_edit.setText(existing['local_path'])
        else:
            # Default to current path if this is the local pane
            if not self.is_remote:
                local_edit.setText(self.current_path)

        remote_edit = QLineEdit()
        remote_edit.setPlaceholderText("/remote/data")
        if existing:
            remote_edit.setText(existing['remote_path'])
        else:
            # Default to current path if this is the remote pane
            if self.is_remote:
                remote_edit.setText(self.current_path)

        direction_combo = QComboBox()
        direction_combo.addItem("⬆ Upload (Local → Remote)", "upload")
        direction_combo.addItem("⬇ Download (Remote → Local)", "download")
        if existing and existing['direction'] == 'download':
            direction_combo.setCurrentIndex(1)

        form.addRow("Name:", name_edit)
        form.addRow("Local Path:", local_edit)
        form.addRow("Remote Path:", remote_edit)
        form.addRow("Direction:", direction_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)

        if dlg.exec_() == QDialog.Accepted:
            name = name_edit.text().strip()
            local_path = local_edit.text().strip()
            remote_path = remote_edit.text().strip()
            direction = direction_combo.currentData()
            if name and local_path and remote_path:
                return {
                    'name': name,
                    'local_path': local_path,
                    'remote_path': remote_path,
                    'direction': direction,
                }
        return None

