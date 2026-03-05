"""Main application window — ties together tabs, menus, status bar, system
tray, and all the backend managers (SSH, SFTP, SLURM, etc.)."""

import logging
import sys
from typing import Optional
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QProgressBar, QSystemTrayIcon, QMenu, QAction, QMessageBox,
    QStatusBar, QApplication
)
from PyQt5.QtCore import Qt, pyqtSlot, QTimer, QSettings, QRect, QSize
from PyQt5.QtGui import QIcon, QFont, QColor

from transfpro.core.ssh_manager import SSHManager
from transfpro.core.sftp_manager import SFTPManager
from transfpro.core.database import Database
from transfpro.core.notification_manager import NotificationManager
from transfpro.core.scheduler import PeriodicScheduler

# Optional SLURM/GROMACS imports — graceful degradation
try:
    from transfpro.core.slurm_manager import SLURMManager
    _HAS_SLURM = True
except ImportError:
    SLURMManager = None
    _HAS_SLURM = False

try:
    from transfpro.core.gromacs_parser import GromacsLogParser
    _HAS_GROMACS = True
except ImportError:
    GromacsLogParser = None
    _HAS_GROMACS = False
from transfpro.config.settings import Settings
from transfpro.config.constants import APP_VERSION
from transfpro.config.themes import DARK_THEME_QSS, LIGHT_THEME_QSS, scale_theme

# Import UI components
from transfpro.ui.widgets.connection_tab import ConnectionTab
# Lazy-imported when tabs are first accessed:
# from transfpro.ui.widgets.job_manager_tab import JobManagerTab
# from transfpro.ui.widgets.file_transfer_tab import FileTransferTab
# from transfpro.ui.widgets.terminal_tab import TerminalTab

# Import dialogs
from transfpro.ui.dialogs.settings_dialog import SettingsDialog
from transfpro.ui.dialogs.about_dialog import AboutDialog
logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """The top-level window. Houses the tab bar, menus, status bar, and
    system tray icon; coordinates SSH/SFTP/SLURM managers behind the scenes."""

    # Constants
    APPLICATION_NAME = "TransfPro"
    APPLICATION_VERSION = APP_VERSION
    ORGANIZATION_NAME = "TransfPro"
    WINDOW_GEOMETRY_KEY = "MainWindow/Geometry"
    WINDOW_STATE_KEY = "MainWindow/State"
    ACTIVE_TAB_KEY = "MainWindow/ActiveTab"

    def __init__(self):
        """Initialize main application window."""
        super().__init__()

        # Set application properties
        self.setWindowTitle(f"{self.APPLICATION_NAME} v{self.APPLICATION_VERSION}")

        # DPI-aware minimum size
        screen = QApplication.primaryScreen()
        if screen:
            dpi = screen.logicalDotsPerInch()
            scale = dpi / 96.0
            self.setMinimumSize(int(1400 * scale), int(900 * scale))
        else:
            self.setMinimumSize(1400, 900)

        logger.info(f"Initializing {self.APPLICATION_NAME} v{self.APPLICATION_VERSION}")

        # Initialize backend managers
        self.ssh_manager = SSHManager()
        self.slurm_manager = SLURMManager(self.ssh_manager) if _HAS_SLURM else None
        self.sftp_manager = SFTPManager(self.ssh_manager)
        self.gromacs_parser = GromacsLogParser() if _HAS_GROMACS else None
        self.database = Database()
        self.settings = Settings()
        self.notification_manager = NotificationManager()
        self.scheduler = PeriodicScheduler()

        # UI components
        self.tabs = {}
        self.dialogs = {}
        self.status_widgets = {}

        # Setup UI
        self._setup_menu_bar()
        self._setup_central_widget()
        self._setup_status_bar()
        self._setup_system_tray()

        # Connect signals
        self._connect_signals()

        # Restore window state
        self._restore_window_state()

        # Apply theme
        self._apply_theme()

        # Setup periodic refresh
        self._setup_refresh_timer()

        logger.info("Main window initialized successfully")

    def _setup_menu_bar(self):
        """Setup application menu bar.

        On macOS the menu bar is placed in the system menu bar.
        Qt automatically moves actions whose role is
        QAction.PreferencesRole / QAction.AboutRole / QAction.QuitRole
        into the application menu, so we set those roles explicitly.
        """
        menubar = self.menuBar()
        is_mac = sys.platform == "darwin"

        # ── File ──
        file_menu = menubar.addMenu("&File")

        new_conn = file_menu.addAction("&New Connection…")
        new_conn.setShortcut("Ctrl+N")
        new_conn.triggered.connect(self._on_new_connection)

        file_menu.addSeparator()

        # Settings / Preferences — on macOS Qt moves this to the app menu
        settings_action = file_menu.addAction("&Preferences…" if is_mac else "&Settings…")
        settings_action.setShortcut("Ctrl+,")
        settings_action.setMenuRole(QAction.PreferencesRole)
        settings_action.triggered.connect(self._on_settings)

        file_menu.addSeparator()

        quit_action = file_menu.addAction("&Quit TransfPro" if is_mac else "E&xit")
        quit_action.setShortcut("Ctrl+Q")
        quit_action.setMenuRole(QAction.QuitRole)
        quit_action.triggered.connect(self.close)

        # ── View ──
        view_menu = menubar.addMenu("&View")

        # Tab navigation
        conn_tab_action = view_menu.addAction("&Connections")
        conn_tab_action.setShortcut("Ctrl+1")
        conn_tab_action.triggered.connect(lambda: self._switch_tab(0))

        files_tab_action = view_menu.addAction("&File Transfer")
        files_tab_action.setShortcut("Ctrl+2")
        files_tab_action.triggered.connect(lambda: self._switch_tab(1))

        terminal_tab_action = view_menu.addAction("&Terminal")
        terminal_tab_action.setShortcut("Ctrl+3")
        terminal_tab_action.triggered.connect(lambda: self._switch_tab(2))

        monitor_tab_action = view_menu.addAction("&Monitoring")
        monitor_tab_action.setShortcut("Ctrl+4")
        monitor_tab_action.triggered.connect(lambda: self._switch_tab(3))

        view_menu.addSeparator()

        refresh_action = view_menu.addAction("&Refresh All")
        refresh_action.setShortcut("Ctrl+R")
        refresh_action.triggered.connect(self._on_refresh_all)

        # ── Help ──
        help_menu = menubar.addMenu("&Help")

        about_action = help_menu.addAction("&About TransfPro")
        about_action.setMenuRole(QAction.AboutRole)
        about_action.triggered.connect(self._on_about)

        help_menu.addSeparator()

        about_qt_action = help_menu.addAction("About &Qt")
        about_qt_action.setMenuRole(QAction.AboutQtRole)
        about_qt_action.triggered.connect(QApplication.aboutQt)

        shortcuts_action = help_menu.addAction("&Keyboard Shortcuts")
        shortcuts_action.triggered.connect(self._on_show_shortcuts)

    def _setup_central_widget(self):
        """Setup central widget with tab interface."""
        central_widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.North)

        # Connection tab — created immediately (needed at startup)
        self.tabs['connection'] = ConnectionTab(self.ssh_manager, self.database)
        self.tab_widget.addTab(self.tabs['connection'], "Connection")

        # ── Lazy tab placeholders (created on first access) ──
        # (internal_name, display_label) — internal_name is used for lazy-loading logic
        self._lazy_tab_indices = {}
        _tab_defs = [
            ("File Transfer", "File Transfer"),
            ("Terminal", "Terminal"),
            ("Job Manager", "Monitoring"),
        ]
        for internal_name, display_label in _tab_defs:
            placeholder = QWidget()
            idx = self.tab_widget.addTab(placeholder, display_label)
            self._lazy_tab_indices[idx] = internal_name

        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        layout.addWidget(self.tab_widget)
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def _setup_status_bar(self):
        """Setup status bar with widgets."""
        status_bar = self.statusBar()

        # Connection status widget
        self.status_widgets['connection'] = QLabel("  Not Connected")
        self.status_widgets['connection'].setStyleSheet(
            "color: #ed8796; font-weight: 700; font-size: 12px; "
            "margin-right: 20px; letter-spacing: 0.3px;"
        )
        status_bar.addWidget(self.status_widgets['connection'])

        # Transfer status widget
        self.status_widgets['transfer'] = QLabel("Ready")
        self.status_widgets['transfer'].setStyleSheet(
            "color: #a6da95; font-size: 12px; margin-right: 20px;"
        )
        status_bar.addPermanentWidget(self.status_widgets['transfer'])

        # General status message
        self.status_widgets['message'] = QLabel("Ready")
        self.status_widgets['message'].setStyleSheet("font-size: 12px;")
        status_bar.addPermanentWidget(self.status_widgets['message'], 1)

    def _setup_system_tray(self):
        """Setup system tray icon and menu."""
        tray_icon = QIcon()
        # Try to load icon, fallback to generic application icon
        try:
            app_icon = self.style().standardIcon(self.style().SP_DialogYesButton)
            self.setWindowIcon(app_icon)
            tray_icon = app_icon
        except Exception as e:
            logger.warning(f"Could not load application icon: {e}")

        # Create system tray icon
        self.tray_icon = QSystemTrayIcon()
        self.tray_icon.setIcon(tray_icon)

        # Create tray context menu
        tray_menu = QMenu()

        show_action = tray_menu.addAction("&Show Window")
        show_action.triggered.connect(self.show_window)

        hide_action = tray_menu.addAction("&Hide Window")
        hide_action.triggered.connect(self.hide_window)

        tray_menu.addSeparator()

        # Quick connections submenu
        connections_submenu = tray_menu.addMenu("Quick &Connect")
        # This will be populated dynamically from saved profiles
        connections_submenu.addAction("(No saved connections)")

        tray_menu.addSeparator()

        exit_action = tray_menu.addAction("E&xit")
        exit_action.triggered.connect(self.close)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

        # Connect tray icon activation
        self.tray_icon.activated.connect(lambda reason: self._on_tray_icon_activated(reason))

    def _connect_signals(self):
        """Connect signals between components."""
        # Connection tab signals (always available at startup)
        if 'connection' in self.tabs:
            self.tabs['connection'].connection_changed.connect(
                self._on_connection_changed
            )
            self.tabs['connection'].profile_changed.connect(
                self._on_profile_changed
            )

        # Other tab signals are connected in _connect_lazy_tab_signals()
        # when each tab is first accessed

        logger.info("Signal connections established")

    def _setup_refresh_timer(self):
        """Setup periodic refresh timer."""
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._on_periodic_refresh)

        # Get refresh interval from settings
        interval = self.settings.get_auto_refresh_interval() * 1000  # Convert to ms
        self.refresh_timer.start(interval)

        logger.info(f"Refresh timer started with {interval}ms interval")

    def _restore_window_state(self):
        """Restore window geometry and state from settings."""
        try:
            # Restore window geometry
            geometry = self.settings.get_window_geometry()
            if geometry and isinstance(geometry, QRect):
                self.setGeometry(geometry)
            else:
                # Default size if no saved geometry
                self.resize(self.settings.get_window_size())

            # Restore window state (minimized/maximized)
            state = self.settings.get_window_state()
            if state:
                self.restoreState(state)

            # Restore active tab
            active_tab = self.settings.get_active_tab_index("MainWindow")
            if 0 <= active_tab < self.tab_widget.count():
                self.tab_widget.setCurrentIndex(active_tab)

            logger.info("Window state restored")

        except Exception as e:
            logger.error(f"Error restoring window state: {e}")

    def _save_window_state(self):
        """Save window geometry and state to settings."""
        try:
            self.settings.set_window_geometry(self.geometry())
            self.settings.set_window_state(self.saveState())
            self.settings.set_active_tab_index("MainWindow", self.tab_widget.currentIndex())
            self.settings.sync()
            logger.info("Window state saved")
        except Exception as e:
            logger.error(f"Error saving window state: {e}")

    def _apply_theme(self, font_size: int = 0):
        """Apply theme from settings, scaling font sizes to *font_size*.

        Scales both the main theme QSS **and** every child widget's inline
        stylesheet so that the entire UI responds to font-size changes.

        Args:
            font_size: Base font size in pt.  0 means read from settings.
        """
        try:
            theme = self.settings.get_theme()
            if theme == "dark":
                stylesheet = DARK_THEME_QSS
            else:
                stylesheet = LIGHT_THEME_QSS

            if font_size <= 0:
                font_size = int(self.settings.get_value(
                    "appearance/font_size", 13))
            stylesheet = scale_theme(stylesheet, font_size)

            self.setStyleSheet(stylesheet)

            # Scale inline stylesheets on all child widgets so that
            # hardcoded font-size values in setStyleSheet() calls
            # are proportionally adjusted.
            self._scale_inline_styles(font_size)

            logger.info(f"Theme '{theme}' applied (font {font_size}pt)")

        except Exception as e:
            logger.error(f"Error applying theme: {e}")

    def _scale_inline_styles(self, font_size: int):
        """Walk every child widget and scale any inline font-size values."""
        from PyQt5.QtWidgets import QWidget
        import re
        _FS_RE = re.compile(r'font-size:\s*(\d+)(px|pt)')
        delta = font_size - 13  # 13 is the authored baseline

        if delta == 0:
            return

        def _scale(m: re.Match) -> str:
            orig = int(m.group(1))
            unit = m.group(2)
            scaled = max(7, orig + delta)
            return f'font-size: {scaled}{unit}'

        for child in self.findChildren(QWidget):
            ss = child.styleSheet()
            if ss and _FS_RE.search(ss):
                scaled_ss = _FS_RE.sub(_scale, ss)
                if scaled_ss != ss:
                    child.setStyleSheet(scaled_ss)

    # Slot methods for menu actions

    @pyqtSlot()
    def _on_new_connection(self):
        """Handle new connection action."""
        if 'connection' in self.tabs:
            self.tab_widget.setCurrentWidget(self.tabs['connection'])
            if hasattr(self.tabs['connection'], '_on_new_connection'):
                self.tabs['connection']._on_new_connection()

    @pyqtSlot()
    def _on_settings(self):
        """Show settings dialog."""
        settings_dialog = SettingsDialog(self.settings, self)
        if settings_dialog.exec_():
            settings_dialog.apply_settings()
            self._apply_theme()
            # Update refresh interval
            interval = self.settings.get_auto_refresh_interval() * 1000
            self.refresh_timer.setInterval(interval)

    @pyqtSlot()
    def _on_refresh_all(self):
        """Refresh all tabs."""
        self.status_widgets['message'].setText("Refreshing...")
        logger.info("Refreshing all tabs")

        try:
            # Refresh job manager
            if 'job_manager' in self.tabs:
                if hasattr(self.tabs['job_manager'], 'refresh'):
                    self.tabs['job_manager'].refresh()

            # Refresh file transfer
            if 'file_transfer' in self.tabs:
                if hasattr(self.tabs['file_transfer'], 'refresh'):
                    self.tabs['file_transfer'].refresh()

            self.status_widgets['message'].setText("Ready")

        except Exception as e:
            logger.error(f"Error refreshing tabs: {e}")
            self.status_widgets['message'].setText(f"Error: {str(e)[:50]}")

    def _switch_tab(self, index: int):
        """Switch to the tab at the given index."""
        if 0 <= index < self.tab_widget.count():
            self.tab_widget.setCurrentIndex(index)

    @pyqtSlot()
    def _on_show_shortcuts(self):
        """Show keyboard shortcuts reference."""
        shortcuts = (
            "<table cellpadding='4' style='font-size: 12px;'>"
            "<tr><td><b>Ctrl+N</b></td><td>New Connection</td></tr>"
            "<tr><td><b>Ctrl+,</b></td><td>Preferences</td></tr>"
            "<tr><td><b>Ctrl+Q</b></td><td>Quit</td></tr>"
            "<tr><td colspan='2'><hr></td></tr>"
            "<tr><td><b>Ctrl+1</b></td><td>Connections tab</td></tr>"
            "<tr><td><b>Ctrl+2</b></td><td>File Transfer tab</td></tr>"
            "<tr><td><b>Ctrl+3</b></td><td>Terminal tab</td></tr>"
            "<tr><td><b>Ctrl+4</b></td><td>Monitoring tab</td></tr>"
            "<tr><td colspan='2'><hr></td></tr>"
            "<tr><td><b>Ctrl+R</b></td><td>Refresh All</td></tr>"
            "</table>"
        )
        QMessageBox.information(self, "Keyboard Shortcuts", shortcuts)

    @pyqtSlot()
    def _on_about(self):
        """Show about dialog."""
        about_dialog = AboutDialog(self)
        about_dialog.exec_()

    # Slot methods for component signals

    @pyqtSlot(bool)
    def _on_connection_changed(self, connected: bool):
        """Handle connection status change."""
        if connected:
            self.status_widgets['connection'].setText("  Connected")
            self.status_widgets['connection'].setStyleSheet(
                "color: #a6da95; font-weight: 700; font-size: 12px; "
                "margin-right: 20px; letter-spacing: 0.3px;"
            )
            logger.info("SSH connection established")

            # Enable other tabs
            for tab_name in ['job_manager', 'file_transfer', 'terminal']:
                if tab_name in self.tabs:
                    self.tab_widget.setTabEnabled(
                        self.tab_widget.indexOf(self.tabs[tab_name]),
                        True
                    )

            # Trigger remote file browser refresh
            if 'file_transfer' in self.tabs:
                try:
                    ft = self.tabs['file_transfer']
                    if hasattr(ft, 'remote_pane'):
                        ft.remote_pane.refresh()
                        logger.info("Remote file browser refreshed after connection")
                except Exception as e:
                    logger.error(f"Error refreshing remote file browser: {e}")

            # Trigger job manager refresh
            if 'job_manager' in self.tabs:
                try:
                    self.tabs['job_manager'].refresh_jobs()
                    logger.info("Job manager refreshed after connection")
                except Exception as e:
                    logger.error(f"Error refreshing job manager: {e}")

            # Auto-connect terminal
            if 'terminal' in self.tabs:
                try:
                    self.tabs['terminal'].connect_terminal()
                except Exception as e:
                    logger.error(f"Error connecting terminal: {e}")

            # Auto-connect mini-terminals in file transfer tab
            if 'file_transfer' in self.tabs:
                ft = self.tabs['file_transfer']
                try:
                    if hasattr(ft, 'local_terminal'):
                        ft.local_terminal.connect_terminal()
                    if hasattr(ft, 'remote_terminal'):
                        ft.remote_terminal.connect_terminal()
                except Exception as e:
                    logger.error(f"Error connecting mini-terminals: {e}")

        else:
            self.status_widgets['connection'].setText("  Not Connected")
            self.status_widgets['connection'].setStyleSheet(
                "color: #ed8796; font-weight: 700; font-size: 12px; "
                "margin-right: 20px; letter-spacing: 0.3px;"
            )
            logger.info("SSH connection lost")

            # Disable other tabs
            for tab_name in ['job_manager', 'file_transfer', 'terminal']:
                if tab_name in self.tabs:
                    self.tab_widget.setTabEnabled(
                        self.tab_widget.indexOf(self.tabs[tab_name]),
                        False
                    )

            # Disconnect and clear terminal
            if 'terminal' in self.tabs:
                try:
                    term = self.tabs['terminal']
                    term.disconnect_terminal()
                    # Clear terminal output so stale content doesn't show
                    # when reconnecting to a different server
                    if hasattr(term, 'terminal_output'):
                        term.terminal_output.clear()
                except Exception as e:
                    logger.error(f"Error disconnecting terminal: {e}")

            # Disconnect mini-terminals and clear remote file browser
            if 'file_transfer' in self.tabs:
                ft = self.tabs['file_transfer']
                try:
                    if hasattr(ft, 'remote_terminal'):
                        ft.remote_terminal.disconnect_terminal()
                        ft.remote_terminal.display.clear()
                    # Clear remote file browser tree so stale files
                    # from previous server don't linger
                    if hasattr(ft, 'remote_pane'):
                        ft.remote_pane.file_tree.clear()
                        ft.remote_pane.current_path = "."
                        ft.remote_pane.path_input.setText(".")
                except Exception as e:
                    logger.error(f"Error cleaning up file transfer tab: {e}")

    def _on_profile_changed(self, *args):
        """Handle profile change."""
        self.status_widgets['message'].setText("Profile changed")

    @pyqtSlot(str)
    def _on_job_status_changed(self, status: str):
        """Handle job status change."""
        self.status_widgets['message'].setText(f"Job: {status}")

    @pyqtSlot()
    def _on_transfer_started(self):
        """Handle file transfer started."""
        self.status_widgets['transfer'].setText("Transferring...")
        self.status_widgets['transfer'].setStyleSheet("color: #7dc4e4;")

    @pyqtSlot()
    def _on_transfer_completed(self):
        """Handle file transfer completed."""
        self.status_widgets['transfer'].setText("Ready")
        self.status_widgets['transfer'].setStyleSheet("color: #a6da95;")

    @pyqtSlot()
    def _on_terminal_connection_lost(self):
        """Handle terminal connection loss."""
        logger.warning("Terminal connection lost")

    def _on_tab_changed(self, index: int):
        """Lazily create tab widgets on first access."""
        if index not in self._lazy_tab_indices:
            return  # Already materialized or connection tab

        tab_name = self._lazy_tab_indices.pop(index)
        old_widget = self.tab_widget.widget(index)

        try:
            if tab_name == "Job Manager":
                from transfpro.ui.widgets.job_manager_tab import JobManagerTab
                widget = JobManagerTab(
                    self.slurm_manager, self.ssh_manager,
                    self.sftp_manager, self.gromacs_parser, self.database
                )
                self.tabs['job_manager'] = widget
            elif tab_name == "File Transfer":
                from transfpro.ui.widgets.file_transfer_tab import FileTransferTab
                widget = FileTransferTab(
                    self.ssh_manager, self.sftp_manager, self.database
                )
                self.tabs['file_transfer'] = widget
            elif tab_name == "Terminal":
                from transfpro.ui.widgets.terminal_tab import TerminalTab
                widget = TerminalTab(self.ssh_manager)
                self.tabs['terminal'] = widget
            else:
                return

            # Replace placeholder with real widget
            _display_labels = {"Job Manager": "Monitoring"}
            display_label = _display_labels.get(tab_name, tab_name)
            self.tab_widget.removeTab(index)
            self.tab_widget.insertTab(index, widget, display_label)
            self.tab_widget.setCurrentIndex(index)

            # Re-connect signals for the new tab
            self._connect_lazy_tab_signals(tab_name)

            # Clean up placeholder
            old_widget.deleteLater()

            logger.info(f"Lazy-loaded tab: {tab_name}")

            # ── Auto-refresh the newly created tab if connected ──
            if self.ssh_manager.is_connected():
                self._initial_tab_refresh(tab_name)

        except Exception as e:
            logger.error(f"Error creating tab {tab_name}: {e}")
            # Put the index back so it can be retried
            self._lazy_tab_indices[index] = tab_name

    def _initial_tab_refresh(self, tab_name: str):
        """Trigger initial data load for a newly-created lazy tab."""
        try:
            if tab_name == "Job Manager" and 'job_manager' in self.tabs:
                self.tabs['job_manager'].refresh_jobs()
                logger.info("Job Manager: initial refresh triggered")
            elif tab_name == "File Transfer" and 'file_transfer' in self.tabs:
                ft = self.tabs['file_transfer']
                if hasattr(ft, 'remote_pane'):
                    ft.remote_pane.refresh()
                    logger.info("File Transfer: remote pane initial refresh triggered")
                # Auto-connect mini-terminals
                if hasattr(ft, 'local_terminal'):
                    ft.local_terminal.connect_terminal()
                    logger.info("File Transfer: local mini-terminal auto-connected")
                if hasattr(ft, 'remote_terminal'):
                    ft.remote_terminal.connect_terminal()
                    logger.info("File Transfer: remote mini-terminal auto-connected")
            elif tab_name == "Terminal" and 'terminal' in self.tabs:
                self.tabs['terminal'].connect_terminal()
                logger.info("Terminal: auto-connect triggered")
        except Exception as e:
            logger.error(f"Error in initial refresh for {tab_name}: {e}")

    def _connect_lazy_tab_signals(self, tab_name: str):
        """Connect signals for a lazily-loaded tab."""
        if tab_name == "Job Manager" and 'job_manager' in self.tabs:
            if hasattr(self.tabs['job_manager'], 'status_changed'):
                self.tabs['job_manager'].status_changed.connect(
                    self._on_job_status_changed
                )
        elif tab_name == "File Transfer" and 'file_transfer' in self.tabs:
            if hasattr(self.tabs['file_transfer'], 'transfer_started'):
                self.tabs['file_transfer'].transfer_started.connect(
                    self._on_transfer_started
                )
            if hasattr(self.tabs['file_transfer'], 'transfer_completed'):
                self.tabs['file_transfer'].transfer_completed.connect(
                    self._on_transfer_completed
                )
        elif tab_name == "Terminal" and 'terminal' in self.tabs:
            if hasattr(self.tabs['terminal'], 'connection_lost'):
                self.tabs['terminal'].connection_lost.connect(
                    self._on_terminal_connection_lost
                )

    def _on_periodic_refresh(self):
        """Handle periodic refresh timer."""
        if not self.ssh_manager.is_connected():
            return
        try:
            # Refresh job manager if visible
            if self.tab_widget.currentWidget() == self.tabs.get('job_manager'):
                if hasattr(self.tabs['job_manager'], 'refresh_jobs'):
                    self.tabs['job_manager'].refresh_jobs()
        except Exception as e:
            logger.debug(f"Error in periodic refresh: {e}")

    def _on_tray_icon_activated(self, reason):
        """Handle system tray icon activation."""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window()
        elif reason == QSystemTrayIcon.Trigger:
            if self.isVisible():
                self.hide_window()
            else:
                self.show_window()

    def show_window(self):
        """Show and raise main window."""
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def hide_window(self):
        """Hide main window to system tray."""
        self.hide()

    def closeEvent(self, event):
        """Handle window close — robust, non-blocking shutdown.

        Key insight: paramiko's Channel.close() can block indefinitely
        waiting for SSH_MSG_CHANNEL_CLOSE acknowledgement.  We NEVER
        call channel.close() on the main thread.  Instead we:

        1. Mark all widgets ``_shutdown_done`` to kill signal cascades.
        2. Tell every reader thread to stop (``_running = False``).
        3. Kill the SSH transport socket to force-unblock all paramiko
           channel operations (recv, recv_ready, close) instantly.
        4. Short wait on threads, force-terminate stragglers.
        5. Full SSH cleanup on a daemon thread (fire-and-forget).
        """
        # ── Re-entrancy guard ──
        # processEvents() or the confirmation dialog can dispatch a
        # second QCloseEvent while we are still inside the first one.
        # The second invocation would race with our cleanup (e.g.
        # os.close(fd) while the first call hasn't finished) and hang.
        if getattr(self, '_close_in_progress', False):
            event.ignore()
            return
        self._close_in_progress = True

        confirm_exit = self.settings.get_value("appearance/confirm_exit", True)
        if confirm_exit:
            reply = QMessageBox.question(
                self,
                f"Exit {self.APPLICATION_NAME}",
                f"Are you sure you want to exit {self.APPLICATION_NAME}?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                self._close_in_progress = False
                event.ignore()
                return

        self._save_window_state()

        try:
            import time
            import threading

            # ── STEP 0: Hide system tray icon ──
            # A visible QSystemTrayIcon keeps the Qt event loop alive
            # even after the last window is closed.  Hide it early.
            if hasattr(self, 'tray_icon') and self.tray_icon:
                self.tray_icon.hide()

            # ── STEP 1: Mark EVERY widget _shutdown_done ──
            self._mark_all_shutdown()

            # ── STEP 2: Disable QPlainTextEdit cursor-blink timers ──
            from PyQt5.QtWidgets import QPlainTextEdit
            for pte in self.findChildren(QPlainTextEdit):
                pte.setCursorWidth(0)
                pte.setReadOnly(True)
                pte.hide()

            # ── STEP 3: Disconnect ALL reader-thread signals ──
            self._disconnect_all_reader_signals()

            # ── STEP 4: Stop timers ──
            self.scheduler.stop_all()
            self.refresh_timer.stop()

            # ── STEP 5: Kill I/O sources FIRST ──
            # This must happen BEFORE we tell threads to quit/stop,
            # because threads blocked on paramiko channel.recv() or
            # SFTP reads will not respond to quit()/stop() until the
            # underlying I/O unblocks.  Killing the socket and local
            # fds makes every blocked read fail instantly with
            # EOFError/OSError.
            self._close_local_fds()
            self._kill_ssh_socket()

            # Detach the disconnected callback so the keepalive timer
            # (if it fires during teardown) does not emit signals into
            # a half-destroyed UI.
            self.ssh_manager.on_disconnected = None

            # ── STEP 6: Signal reader threads to stop ──
            all_threads = []
            self._signal_all_readers_stop(all_threads)

            # ── STEP 7: Collect and quit all worker QThreads ──
            jm = self.tabs.get('job_manager')
            if jm:
                if getattr(jm, 'refresh_timer', None):
                    jm.refresh_timer.stop()
                if getattr(jm, 'query_worker', None):
                    try:
                        jm.query_worker.cancel()
                    except RuntimeError:
                        pass
                for t in [getattr(jm, 'query_thread', None),
                          getattr(jm, 'cancel_thread', None)]:
                    if t and t.isRunning():
                        t.quit()
                        all_threads.append(t)

            ct = self.tabs.get('connection')
            if ct:
                if hasattr(ct, '_anim_timer'):
                    ct._anim_timer.stop()
                for attr in ('connection_thread', '_disconnect_thread'):
                    t = getattr(ct, attr, None)
                    if t and t.isRunning():
                        t.quit()
                        all_threads.append(t)

            ft = self.tabs.get('file_transfer')
            if ft:
                for worker in list(getattr(ft, 'transfer_workers', {}).values()):
                    try:
                        worker.cancel()
                    except RuntimeError:
                        pass
                for t in list(getattr(ft, 'transfer_threads', {}).values()):
                    if t.isRunning():
                        t.quit()
                        all_threads.append(t)

                for pane_name in ('local_pane', 'remote_pane'):
                    pane = getattr(ft, pane_name, None)
                    if pane:
                        bt = getattr(pane, '_browser_thread', None)
                        if bt and bt.isRunning():
                            bt.quit()
                            all_threads.append(bt)

            # ── STEP 8: Wait for threads (0.5 s budget) ──
            # With the socket already dead, blocked I/O has already
            # failed and threads should exit almost immediately.
            deadline = time.monotonic() + 0.5
            for t in all_threads:
                remaining = max(0, int((deadline - time.monotonic()) * 1000))
                if t.isRunning() and remaining > 0:
                    t.wait(remaining)

            # ── STEP 9: Force-terminate stragglers ──
            for t in all_threads:
                if t.isRunning():
                    logger.warning(f"Force-terminating thread: {t}")
                    t.terminate()

            # ── STEP 10: Null out Qt objects ──
            if ft:
                for pane_name in ('local_pane', 'remote_pane'):
                    pane = getattr(ft, pane_name, None)
                    if pane:
                        pane._browser_thread = None
                        pane._browser_worker = None
                ft.transfer_threads.clear()
                ft.transfer_workers.clear()

            # ── STEP 11: Full SSH cleanup on daemon thread ──
            threading.Thread(
                target=self.ssh_manager.disconnect, daemon=True
            ).start()

            logger.info("Application closing")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

        event.accept()

        # Ensure the Qt event loop exits even if something (e.g. an
        # orphaned timer or hidden widget) would otherwise keep it alive.
        QApplication.instance().quit()

        # ── Last-resort hard exit ──
        # If QApplication.quit() fails to terminate the event loop
        # (e.g. a QThread or system-tray artefact keeps it alive),
        # or if Python's shutdown hangs on threading._shutdown() /
        # paramiko's atexit handler, force-kill the process.
        # Uses a daemon thread so it doesn't block normal exit.
        import os as _os
        def _force_exit():
            import time
            time.sleep(2)
            _os._exit(0)
        threading.Thread(target=_force_exit, daemon=True).start()

    def _disconnect_all_reader_signals(self):
        """Disconnect every reader-thread signal to prevent new queuing."""
        # Full terminal tab
        tt = self.tabs.get('terminal')
        if tt:
            reader = getattr(tt, 'reader_thread', None)
            if reader:
                for sig_name in ('data_received', 'error_occurred',
                                 'channel_closed'):
                    sig = getattr(reader, sig_name, None)
                    if sig:
                        try:
                            sig.disconnect()
                        except (TypeError, RuntimeError):
                            pass

        # Mini-terminals inside file_transfer tab
        ft = self.tabs.get('file_transfer')
        if ft:
            for term_name in ('local_terminal', 'remote_terminal'):
                term = getattr(ft, term_name, None)
                if not term:
                    continue
                reader = getattr(term, '_reader', None)
                if reader:
                    for sig_name in ('data_received', 'closed'):
                        sig = getattr(reader, sig_name, None)
                        if sig:
                            try:
                                sig.disconnect()
                            except (TypeError, RuntimeError):
                                pass

    def _signal_all_readers_stop(self, all_threads):
        """Set _running = False on every reader thread (non-blocking).

        Collects the QThread objects into ``all_threads`` for later
        wait/terminate.  Does NOT call channel.close() — that can
        block on network I/O.
        """
        # Terminal tab reader
        tt = self.tabs.get('terminal')
        if tt:
            reader = getattr(tt, 'reader_thread', None)
            if reader:
                reader._running = False
                if reader.isRunning():
                    all_threads.append(reader)

        # Mini-terminal readers
        ft = self.tabs.get('file_transfer')
        if ft:
            for term_name in ('local_terminal', 'remote_terminal'):
                term = getattr(ft, term_name, None)
                if not term:
                    continue
                reader = getattr(term, '_reader', None)
                if reader:
                    reader._running = False
                    if reader.isRunning():
                        all_threads.append(reader)

    def _close_local_fds(self):
        """Kill local subprocesses and close PTY file descriptors.

        IMPORTANT: Kill the subprocess FIRST, then close the fd.
        On macOS, calling os.close(fd) while another thread is blocked
        in os.read(fd) has undefined behaviour and can deadlock.
        Killing the process closes the slave end of the PTY, which
        sends EOF to the master end, unblocking the reader thread's
        os.read() — only then is it safe to close the master fd.
        """
        import os
        import signal
        ft = self.tabs.get('file_transfer')
        if not ft:
            return
        for term_name in ('local_terminal', 'remote_terminal'):
            term = getattr(ft, term_name, None)
            if not term:
                continue

            # Kill subprocess FIRST — this unblocks os.read() on the
            # master fd by closing the slave end of the PTY.
            proc = getattr(term, '_process', None)
            if proc:
                try:
                    # Kill the entire process group (setsid was used at
                    # spawn time) so child processes also die.
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
                try:
                    proc.wait(timeout=0.2)
                except Exception:
                    pass
                term._process = None

            fd = getattr(term, '_master_fd', -1)
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
                term._master_fd = -1

    def _kill_ssh_socket(self):
        """Shut down the raw TCP socket under the SSH transport.

        This force-unblocks every paramiko channel operation (recv,
        recv_ready, close) instantly without waiting for SSH protocol
        handshakes.  The transport will raise EOFError / OSError in
        any thread that's blocked on channel I/O.
        """
        import socket
        try:
            transport = (
                self.ssh_manager._transport
                or (self.ssh_manager._client.get_transport()
                    if self.ssh_manager._client else None)
            )
            if transport and hasattr(transport, 'sock') and transport.sock:
                try:
                    transport.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    transport.sock.close()
                except OSError:
                    pass
        except Exception:
            pass

    def _mark_all_shutdown(self):
        """Recursively mark every tab and nested widget as shutting down.

        This must happen BEFORE any cleanup so that signal handlers
        (auto-reconnect, connection_changed cascades, channel_closed
        handlers) immediately bail out instead of starting new work.
        """
        # Top-level tabs
        for tab in self.tabs.values():
            tab._shutdown_done = True

        # Nested widgets inside file_transfer tab
        ft = self.tabs.get('file_transfer')
        if ft:
            for attr in ('local_pane', 'remote_pane',
                         'local_terminal', 'remote_terminal'):
                widget = getattr(ft, attr, None)
                if widget:
                    widget._shutdown_done = True

        # Terminal tab itself
        tt = self.tabs.get('terminal')
        if tt:
            tt._shutdown_done = True

    def changeEvent(self, event):
        """Handle window state changes."""
        from PyQt5.QtCore import QEvent

        if event.type() == QEvent.WindowStateChange:
            if self.windowState() & Qt.WindowMinimized:
                # Auto-hide to tray when minimized (if enabled)
                if self.settings.get_value("appearance/minimize_to_tray", False):
                    self.hide()

        super().changeEvent(event)
