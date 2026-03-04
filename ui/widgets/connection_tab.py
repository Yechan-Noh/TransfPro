"""Connection Manager tab — profile list with cluster-icon cards, SSH
connect/disconnect controls, status display, and connection log."""

import logging
import os
from typing import Optional, List
from datetime import datetime
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGroupBox,
    QFormLayout, QLabel, QPlainTextEdit, QMessageBox, QSplitter,
    QLineEdit, QCheckBox, QDialog, QSizePolicy, QInputDialog,
    QGridLayout, QScrollArea
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QSize, QEvent, QTimer
from PyQt5.QtGui import QIcon, QColor, QFont, QPixmap, QPainter

from transfpro.models.connection import ConnectionProfile
from transfpro.core.ssh_manager import SSHManager
from transfpro.core.database import Database
from transfpro.workers.ssh_connect_worker import SSHConnectWorker, SSHDisconnectWorker
from transfpro.ui.dialogs.connection_dialog import ConnectionDialog
from transfpro.ui.widgets.status_indicators import StatusLight

logger = logging.getLogger(__name__)


class ConnectionTab(QWidget):
    """Manages SSH connection profiles and handles connect/disconnect flow."""

    connection_changed = pyqtSignal(bool)  # True=connected
    profile_changed = pyqtSignal(ConnectionProfile)
    _server_disconnected = pyqtSignal()  # thread-safe disconnect notify

    def __init__(self, ssh_manager: SSHManager, database: Database, parent=None):
        super().__init__(parent)
        self.ssh_manager = ssh_manager
        self.database = database
        self.profiles: List[ConnectionProfile] = []
        self.current_profile: Optional[ConnectionProfile] = None
        self.is_connected = False
        self.connection_thread: Optional[QThread] = None
        self.connection_worker: Optional[SSHConnectWorker] = None

        self._setup_ui()
        self._load_profiles()
        self._setup_connections()

    def _setup_ui(self):
        """Set up the UI layout."""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Content area with splitter
        content_splitter = QSplitter(Qt.Horizontal)
        content_splitter.setHandleWidth(1)

        # Left panel: Profile list + action buttons
        left_panel = self._create_left_panel()
        content_splitter.addWidget(left_panel)

        # Right panel: Connection details + controls
        right_panel = self._create_right_panel()
        content_splitter.addWidget(right_panel)

        # Set initial sizes (75% / 25%)
        content_splitter.setSizes([750, 250])
        content_splitter.setCollapsible(0, False)
        content_splitter.setCollapsible(1, False)

        main_layout.addWidget(content_splitter, 1)

        # Bottom: Connection log
        log_card = self._create_log_card()
        main_layout.addWidget(log_card)

        self.setLayout(main_layout)

    # ── Cluster card style constants ──

    _CARD_STYLE = """
        QPushButton {{
            background: {bg};
            border: 2px solid {border};
            border-radius: 10px;
            padding: 6px 6px;
            min-height: 48px;
            min-width: 80px;
            text-align: center;
        }}
        QPushButton:hover {{
            background: {hover_bg};
            border-color: {hover_border};
        }}
        QPushButton:pressed {{
            background: {pressed_bg};
        }}
    """

    _CARD_SELECTED_STYLE = """
        QPushButton {{
            background: {bg};
            border: 2px solid {border};
            border-radius: 10px;
            padding: 6px 6px;
            min-height: 48px;
            min-width: 80px;
            text-align: center;
        }}
        QPushButton:hover {{
            background: {hover_bg};
            border-color: {hover_border};
        }}
    """

    # Color palettes for cluster cards
    _CARD_COLORS = [
        {  # teal
            'icon_bg': '#0ea5e9', 'icon_fg': '#ffffff',
            'bg': 'rgba(14, 165, 233, 0.06)', 'border': 'rgba(14, 165, 233, 0.15)',
            'hover_bg': 'rgba(14, 165, 233, 0.12)', 'hover_border': 'rgba(14, 165, 233, 0.4)',
            'pressed_bg': 'rgba(14, 165, 233, 0.18)',
            'sel_bg': 'rgba(14, 165, 233, 0.15)', 'sel_border': '#0ea5e9',
            'sel_hover_bg': 'rgba(14, 165, 233, 0.2)', 'sel_hover_border': '#0ea5e9',
        },
        {  # green
            'icon_bg': '#a6da95', 'icon_fg': '#1e2030',
            'bg': 'rgba(166, 218, 149, 0.06)', 'border': 'rgba(166, 218, 149, 0.15)',
            'hover_bg': 'rgba(166, 218, 149, 0.12)', 'hover_border': 'rgba(166, 218, 149, 0.4)',
            'pressed_bg': 'rgba(166, 218, 149, 0.18)',
            'sel_bg': 'rgba(166, 218, 149, 0.15)', 'sel_border': '#a6da95',
            'sel_hover_bg': 'rgba(166, 218, 149, 0.2)', 'sel_hover_border': '#a6da95',
        },
        {  # purple
            'icon_bg': '#c6a0f6', 'icon_fg': '#1e2030',
            'bg': 'rgba(198, 160, 246, 0.06)', 'border': 'rgba(198, 160, 246, 0.15)',
            'hover_bg': 'rgba(198, 160, 246, 0.12)', 'hover_border': 'rgba(198, 160, 246, 0.4)',
            'pressed_bg': 'rgba(198, 160, 246, 0.18)',
            'sel_bg': 'rgba(198, 160, 246, 0.15)', 'sel_border': '#c6a0f6',
            'sel_hover_bg': 'rgba(198, 160, 246, 0.2)', 'sel_hover_border': '#c6a0f6',
        },
        {  # orange
            'icon_bg': '#f5a97f', 'icon_fg': '#1e2030',
            'bg': 'rgba(245, 169, 127, 0.06)', 'border': 'rgba(245, 169, 127, 0.15)',
            'hover_bg': 'rgba(245, 169, 127, 0.12)', 'hover_border': 'rgba(245, 169, 127, 0.4)',
            'pressed_bg': 'rgba(245, 169, 127, 0.18)',
            'sel_bg': 'rgba(245, 169, 127, 0.15)', 'sel_border': '#f5a97f',
            'sel_hover_bg': 'rgba(245, 169, 127, 0.2)', 'sel_hover_border': '#f5a97f',
        },
        {  # pink
            'icon_bg': '#f5bde6', 'icon_fg': '#1e2030',
            'bg': 'rgba(245, 189, 230, 0.06)', 'border': 'rgba(245, 189, 230, 0.15)',
            'hover_bg': 'rgba(245, 189, 230, 0.12)', 'hover_border': 'rgba(245, 189, 230, 0.4)',
            'pressed_bg': 'rgba(245, 189, 230, 0.18)',
            'sel_bg': 'rgba(245, 189, 230, 0.15)', 'sel_border': '#f5bde6',
            'sel_hover_bg': 'rgba(245, 189, 230, 0.2)', 'sel_hover_border': '#f5bde6',
        },
        {  # yellow
            'icon_bg': '#eed49f', 'icon_fg': '#1e2030',
            'bg': 'rgba(238, 212, 159, 0.06)', 'border': 'rgba(238, 212, 159, 0.15)',
            'hover_bg': 'rgba(238, 212, 159, 0.12)', 'hover_border': 'rgba(238, 212, 159, 0.4)',
            'pressed_bg': 'rgba(238, 212, 159, 0.18)',
            'sel_bg': 'rgba(238, 212, 159, 0.15)', 'sel_border': '#eed49f',
            'sel_hover_bg': 'rgba(238, 212, 159, 0.2)', 'sel_hover_border': '#eed49f',
        },
    ]

    # Cached fonts for icon rendering (created once, reused)
    _icon_fonts = {}  # {pixel_size: QFont}

    def _make_cluster_icon(self, initials: str, bg_color: str, fg_color: str,
                           size: int = 36) -> QPixmap:
        """Create a rounded-rect icon with initials for a cluster card."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Background circle
        painter.setBrush(QColor(bg_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, size, size, size // 2, size // 2)

        # Initials text — reuse cached font
        painter.setPen(QColor(fg_color))
        px = size // 3
        if px not in self._icon_fonts:
            font = QFont()
            font.setPixelSize(px)
            font.setBold(True)
            self._icon_fonts[px] = font
        painter.setFont(self._icon_fonts[px])
        painter.drawText(0, 0, size, size, Qt.AlignCenter, initials[:3])
        painter.end()
        return pixmap

    def _create_left_panel(self) -> QWidget:
        """Create the left panel with cluster icon grid and action buttons."""
        panel = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(10)

        # Header with title — relative to app font so it scales with settings
        header = QLabel("Connections")
        header_font = QFont(header.font())
        header_font.setPointSize(header_font.pointSize() + 4)
        header_font.setWeight(QFont.Black)
        header.setFont(header_font)
        header.setStyleSheet(
            "letter-spacing: 0.3px; padding: 4px 0px;"
        )
        layout.addWidget(header)

        # Scrollable grid area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
        """)

        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(8)
        self._grid_layout.setContentsMargins(4, 4, 4, 4)
        # Force all 3 columns to equal width
        self._grid_layout.setColumnStretch(0, 1)
        self._grid_layout.setColumnStretch(1, 1)
        self._grid_layout.setColumnStretch(2, 1)
        self._card_buttons = []
        self._selected_card_index = -1

        scroll.setWidget(self._grid_container)
        layout.addWidget(scroll, 1)

        # Action buttons are created here but placed inside the grid by _rebuild_card_grid
        self.new_button = QPushButton("+ New")
        self.new_button.setToolTip("Create a new connection profile")
        self.new_button.setCursor(Qt.PointingHandCursor)
        self.new_button.clicked.connect(self._on_new_connection)

        self.edit_button = QPushButton("Edit")
        self.edit_button.setToolTip("Edit selected profile")
        self.edit_button.setEnabled(False)
        self.edit_button.setCursor(Qt.PointingHandCursor)
        self.edit_button.clicked.connect(self._on_edit_connection)

        self.delete_button = QPushButton("Delete")
        self.delete_button.setObjectName("dangerButton")
        self.delete_button.setToolTip("Delete selected profile")
        self.delete_button.setEnabled(False)
        self.delete_button.setCursor(Qt.PointingHandCursor)
        self.delete_button.clicked.connect(self._on_delete_connection)

        panel.setLayout(layout)
        return panel

    def _rebuild_card_grid(self):
        """Rebuild the cluster icon grid from current profiles."""
        # Reparent buttons so they survive the grid clear
        self.new_button.setParent(self)
        self.edit_button.setParent(self)
        self.delete_button.setParent(self)
        self.new_button.hide()
        self.edit_button.hide()
        self.delete_button.hide()

        # Clear all widgets from grid
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._card_buttons.clear()

        cols = 3
        for idx, profile in enumerate(self.profiles):
            row = idx // cols
            col = idx % cols
            colors = self._CARD_COLORS[idx % len(self._CARD_COLORS)]

            # Generate initials from profile name
            words = profile.name.split()
            if len(words) >= 2:
                initials = words[0][0].upper() + words[1][0].upper()
            else:
                initials = profile.name[:2].upper()

            icon_pixmap = self._make_cluster_icon(
                initials, colors['icon_bg'], colors['icon_fg']
            )

            card = QPushButton()
            card.setIcon(QIcon(icon_pixmap))
            card.setIconSize(QSize(36, 36))
            card.setCursor(Qt.PointingHandCursor)
            card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

            # Build label text (no leading newline so text centers vertically with icon)
            label_text = (
                f"{profile.name}\n"
                f"{profile.username}@{profile.host}"
            )
            card.setText(label_text)
            card.setStyleSheet(self._CARD_STYLE.format(**colors))

            # Click to select, double-click to connect
            card.clicked.connect(lambda checked, i=idx: self._on_card_clicked(i))
            card.installEventFilter(self)
            card.setProperty("card_index", idx)

            self._card_buttons.append((card, colors))
            self._grid_layout.addWidget(card, row, col)

        # Place action buttons in column 0, row after last card
        btn_row = (len(self.profiles) // cols) + (1 if len(self.profiles) % cols != 0 else 0)
        if not self.profiles:
            btn_row = 0

        # Wrap buttons in a horizontal row that fits one column width
        btn_container = QWidget()
        btn_lay = QHBoxLayout(btn_container)
        btn_lay.setContentsMargins(0, 0, 0, 0)
        btn_lay.setSpacing(4)
        btn_lay.addWidget(self.new_button)
        btn_lay.addWidget(self.edit_button)
        btn_lay.addWidget(self.delete_button)
        self.new_button.show()
        self.edit_button.show()
        self.delete_button.show()
        self._grid_layout.addWidget(btn_container, btn_row, 0)

        # Add spacer below everything
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._grid_layout.addWidget(spacer, btn_row + 1, 0, 1, cols)

    def _on_card_clicked(self, index: int):
        """Handle clicking on a cluster card."""
        if index < 0 or index >= len(self.profiles):
            return

        self._selected_card_index = index
        self.current_profile = self.profiles[index]

        # Update card styles (highlight selected)
        for i, (card, colors) in enumerate(self._card_buttons):
            if i == index:
                card.setStyleSheet(self._CARD_SELECTED_STYLE.format(
                    bg=colors['sel_bg'], border=colors['sel_border'],
                    hover_bg=colors['sel_hover_bg'],
                    hover_border=colors['sel_hover_border'],
                    pressed_bg=colors.get('pressed_bg', colors['sel_bg']),
                ))
            else:
                card.setStyleSheet(self._CARD_STYLE.format(**colors))

        self._update_details_display()
        self.edit_button.setEnabled(True)
        self.delete_button.setEnabled(True)
        if not self.is_connected:
            self._update_button_states(connect_enabled=True, disconnect_enabled=False)

    def _on_card_double_clicked(self, index: int):
        """Handle double-clicking on a cluster card to connect."""
        self._on_card_clicked(index)
        if self.connect_button.isEnabled():
            self._on_connect()

    def eventFilter(self, obj, event):
        """Catch double-click on cluster cards to trigger connect."""
        if event.type() == QEvent.MouseButtonDblClick:
            idx = obj.property("card_index")
            if idx is not None:
                self._on_card_double_clicked(idx)
                return True
        return super().eventFilter(obj, event)

    def _create_right_panel(self) -> QWidget:
        """Create the right panel with connection details and controls."""
        panel = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(14)

        # ── Status Card ──
        status_card = QGroupBox("Status")
        status_layout = QVBoxLayout()
        status_layout.setSpacing(14)

        # Status indicator row
        status_row = QHBoxLayout()
        self.status_light = StatusLight(color="red", size=14)
        status_row.addWidget(self.status_light)

        self.status_text = QLabel("Not connected")
        status_font = QFont(self.status_text.font())
        status_font.setPointSize(status_font.pointSize() + 2)
        status_font.setWeight(QFont.Bold)
        self.status_text.setFont(status_font)
        self.status_text.setStyleSheet("letter-spacing: 0.2px;")
        status_row.addWidget(self.status_text)
        status_row.addStretch()
        status_layout.addLayout(status_row)

        # Connection details grid
        details_form = QFormLayout()
        details_form.setSpacing(10)
        details_form.setHorizontalSpacing(20)
        details_form.setLabelAlignment(Qt.AlignLeft)

        value_style = "font-weight: 600;"

        self.detail_host = QLabel("—")
        self.detail_host.setStyleSheet(value_style)
        details_form.addRow("Host", self.detail_host)

        self.detail_port = QLabel("—")
        self.detail_port.setStyleSheet(value_style)
        details_form.addRow("Port", self.detail_port)

        self.detail_username = QLabel("—")
        self.detail_username.setStyleSheet(value_style)
        details_form.addRow("Username", self.detail_username)

        self.detail_auth_method = QLabel("—")
        self.detail_auth_method.setStyleSheet(value_style)
        details_form.addRow("Auth", self.detail_auth_method)

        status_layout.addLayout(details_form)
        status_card.setLayout(status_layout)
        layout.addWidget(status_card)

        # ── 2FA Card ──
        twofa_card = QGroupBox("Two-Factor Auth")
        twofa_layout = QVBoxLayout()
        twofa_layout.setSpacing(10)

        self.detail_2fa_enabled = QCheckBox("2FA Enabled")
        self.detail_2fa_enabled.setEnabled(False)
        twofa_layout.addWidget(self.detail_2fa_enabled)

        twofa_form = QFormLayout()
        twofa_form.setSpacing(8)
        twofa_form.setHorizontalSpacing(20)
        twofa_form.setLabelAlignment(Qt.AlignLeft)

        self.detail_2fa_response = QLabel("—")
        self.detail_2fa_response.setStyleSheet("font-weight: 600;")
        twofa_form.addRow("Response", self.detail_2fa_response)

        self.detail_2fa_timeout = QLabel("—")
        self.detail_2fa_timeout.setStyleSheet("font-weight: 600;")
        twofa_form.addRow("Timeout", self.detail_2fa_timeout)

        twofa_layout.addLayout(twofa_form)
        twofa_card.setLayout(twofa_layout)
        layout.addWidget(twofa_card)

        # ── Connect / Disconnect buttons ──
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)

        # ── Style sheets for button states ──
        self._connect_active_style = """
            QPushButton {
                font-weight: 800;
                background-color: #3ba55d; color: #ffffff;
                border: none; border-radius: 6px; padding: 8px 16px;
            }
            QPushButton:hover { background-color: #2d8049; }
            QPushButton:pressed { background-color: #246b3c; }
        """
        self._connect_disabled_style = """
            QPushButton {
                font-weight: 800;
                background-color: #3b3f4a; color: #6e738d;
                border: none; border-radius: 6px; padding: 8px 16px;
            }
        """
        self._disconnect_active_style = """
            QPushButton {
                font-weight: 800;
                background-color: #d94343; color: #ffffff;
                border: none; border-radius: 6px; padding: 8px 16px;
            }
            QPushButton:hover { background-color: #b53636; }
            QPushButton:pressed { background-color: #942c2c; }
        """
        self._disconnect_disabled_style = """
            QPushButton {
                font-weight: 800;
                background-color: #3b3f4a; color: #6e738d;
                border: none; border-radius: 6px; padding: 8px 16px;
            }
        """

        self.connect_button = QPushButton("Connect")
        self.connect_button.setObjectName("successButton")
        self.connect_button.setMinimumWidth(140)
        self.connect_button.setMinimumHeight(42)
        self.connect_button.setEnabled(False)
        self.connect_button.setCursor(Qt.PointingHandCursor)
        self.connect_button.setStyleSheet(self._connect_disabled_style)
        self.connect_button.clicked.connect(self._on_connect)
        action_layout.addWidget(self.connect_button)

        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.setMinimumWidth(140)
        self.disconnect_button.setMinimumHeight(42)
        self.disconnect_button.setEnabled(False)
        self.disconnect_button.setCursor(Qt.PointingHandCursor)
        self.disconnect_button.setStyleSheet(self._disconnect_disabled_style)
        self.disconnect_button.clicked.connect(self._on_disconnect)
        action_layout.addWidget(self.disconnect_button)

        action_layout.addStretch()
        layout.addLayout(action_layout)

        layout.addStretch()

        panel.setLayout(layout)
        return panel

    def _create_log_card(self) -> QWidget:
        """Create the connection log card."""
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout()
        log_layout.setContentsMargins(10, 14, 10, 10)
        log_layout.setSpacing(0)

        self.log_widget = QPlainTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setMaximumBlockCount(500)  # Auto-trim old lines (O(1))
        self.log_widget.setMaximumHeight(130)
        self.log_widget.setStyleSheet(
            "QPlainTextEdit {"
            "  background-color: #1a1b26;"
            "  color: #a6da95;"
            "  font-family: 'Menlo', 'Monaco', 'Fira Code', 'Courier New', monospace;"
            "  font-size: 11px;"
            "  border: none;"
            "  border-radius: 6px;"
            "  padding: 10px;"
            "}"
        )
        log_layout.addWidget(self.log_widget)
        log_group.setLayout(log_layout)
        return log_group

    def _setup_connections(self):
        """Set up signal-slot connections."""
        # Thread-safe: keepalive thread emits signal → main thread slot
        self._server_disconnected.connect(self._on_ssh_disconnected)
        if self.ssh_manager:
            self.ssh_manager.on_connected = lambda: self._on_ssh_connected()
            # Use signal emission for thread safety — on_disconnected may be
            # called from the keepalive timer thread on server-side drops
            self.ssh_manager.on_disconnected = lambda: self._server_disconnected.emit()
            self.ssh_manager.on_error = lambda msg: self._log_message(f"SSH Error: {msg}")

    # ── Password persistence (system keyring) ──

    _KEYRING_SERVICE = "TransfPro"

    @staticmethod
    def _pw_key(profile: ConnectionProfile) -> str:
        return f"{profile.username}@{profile.host}:{profile.port}"

    def _save_password(self, profile: ConnectionProfile, password: str):
        """Save password to system keyring (macOS Keychain, etc.)."""
        try:
            import keyring
            keyring.set_password(
                self._KEYRING_SERVICE,
                self._pw_key(profile),
                password,
            )
            logger.debug("Password saved to system keyring")
        except Exception as e:
            logger.warning(f"Could not save password to keyring: {e}")

    def _load_password(self, profile: ConnectionProfile) -> Optional[str]:
        """Load a saved password from system keyring."""
        try:
            import keyring
            return keyring.get_password(
                self._KEYRING_SERVICE,
                self._pw_key(profile),
            )
        except Exception as e:
            logger.warning(f"Could not load password from keyring: {e}")
            return None

    def _delete_password(self, profile: ConnectionProfile):
        """Delete a saved password from system keyring."""
        try:
            import keyring
            keyring.delete_password(
                self._KEYRING_SERVICE,
                self._pw_key(profile),
            )
            logger.debug("Password deleted from system keyring")
        except Exception as e:
            logger.debug(f"Could not delete password from keyring: {e}")

    def _load_profiles(self):
        """Load connection profiles from database."""
        try:
            self.profiles = []

            # Load saved profiles from database
            if self.database:
                db_profiles = self.database.get_all_profiles()
                for row in db_profiles:
                    profile = ConnectionProfile(
                        name=row.get('name', ''),
                        host=row.get('hostname', ''),
                        port=row.get('port', 22),
                        username=row.get('username', ''),
                        auth_method="key" if row.get('use_key') else "password",
                        key_path=row.get('key_path'),
                        has_2fa=bool(row.get('has_2fa', False)),
                        two_fa_response=row.get('two_fa_response', '1'),
                        two_fa_timeout=row.get('two_fa_timeout', 60),
                        keepalive_interval=row.get('keep_alive_interval', 30),
                    )
                    profile.id = row.get('id', profile.id)
                    self.profiles.append(profile)

            # Restore saved passwords
            restored = 0
            for profile in self.profiles:
                saved_pw = self._load_password(profile)
                if saved_pw:
                    profile._stored_password = saved_pw
                    restored += 1

            self._update_profile_list()
            n = len(self.profiles)
            if n > 0:
                msg = f"Loaded {n} saved profile{'s' if n != 1 else ''}"
                if restored:
                    msg += f" ({restored} with saved password)"
                self._log_message(msg)
            else:
                self._log_message(
                    "No saved profiles. Click '+ New' to add a connection."
                )
        except Exception as e:
            logger.error(f"Error loading profiles: {e}")
            self._log_message(f"Error loading profiles: {e}")

    def _update_profile_list(self):
        """Rebuild the cluster card grid."""
        self._rebuild_card_grid()

    def _update_details_display(self):
        """Update the details panel."""
        if not self.current_profile:
            self._clear_details()
            return

        self.detail_host.setText(self.current_profile.host)
        self.detail_port.setText(str(self.current_profile.port))
        self.detail_username.setText(self.current_profile.username)

        auth_method = "SSH Key" if self.current_profile.auth_method == "key" else "Password"
        self.detail_auth_method.setText(auth_method)

        self.detail_2fa_enabled.setChecked(self.current_profile.has_2fa)
        self.detail_2fa_response.setText(self.current_profile.two_fa_response)
        self.detail_2fa_timeout.setText(f"{self.current_profile.two_fa_timeout} sec")

    def _clear_details(self):
        """Clear the details display."""
        self.detail_host.setText("—")
        self.detail_port.setText("—")
        self.detail_username.setText("—")
        self.detail_auth_method.setText("—")
        self.detail_2fa_enabled.setChecked(False)
        self.detail_2fa_response.setText("—")
        self.detail_2fa_timeout.setText("—")

    # ── Profile CRUD ──

    def _on_new_connection(self):
        """Handle new connection button click."""
        dialog = ConnectionDialog(profile=None, parent=self)
        if dialog.exec() == QDialog.Accepted:
            profile = dialog.get_profile()
            # Persist to database
            if self.database:
                try:
                    self.database.save_profile(profile)
                except Exception as e:
                    logger.warning(f"Could not save profile to database: {e}")
            self.profiles.append(profile)
            self._update_profile_list()
            self._log_message(f"Created profile: {profile.name}")
            self.profile_changed.emit(profile)

    def _on_edit_connection(self):
        """Handle edit button click."""
        if not self.current_profile:
            return

        dialog = ConnectionDialog(profile=self.current_profile, parent=self)
        if dialog.exec() == QDialog.Accepted:
            updated = dialog.get_profile()
            # Persist to database
            if self.database:
                try:
                    self.database.save_profile(updated)
                except Exception as e:
                    logger.warning(f"Could not update profile in database: {e}")
            idx = next(
                (i for i, p in enumerate(self.profiles) if p.id == updated.id), -1
            )
            if idx >= 0:
                self.profiles[idx] = updated
                self.current_profile = updated
            self._update_profile_list()
            self._update_details_display()
            self._log_message(f"Updated profile: {updated.name}")
            self.profile_changed.emit(updated)

    def _on_delete_connection(self):
        """Handle delete button click."""
        if not self.current_profile:
            return

        reply = QMessageBox.warning(
            self, "Delete Connection",
            f"Delete '{self.current_profile.name}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            name = self.current_profile.name
            profile_id = self.current_profile.id
            # Delete password from system keyring
            self._delete_password(self.current_profile)
            # Delete from database
            if self.database:
                try:
                    self.database.delete_profile(profile_id)
                except Exception as e:
                    logger.warning(f"Could not delete profile from database: {e}")
            self.profiles = [p for p in self.profiles if p.id != profile_id]
            self.current_profile = None
            self._update_profile_list()
            self._clear_details()
            self._log_message(f"Deleted profile: {name}")

    # ── Connection ──

    # Style for the cancel button shown while connecting
    _cancel_active_style = """
        QPushButton {
            font-weight: 800;
            background-color: #e5a00d; color: #ffffff;
            border: none; border-radius: 6px; padding: 8px 16px;
        }
        QPushButton:hover { background-color: #c78c0b; }
        QPushButton:pressed { background-color: #a87509; }
    """

    def _update_button_states(self, connect_enabled: bool, disconnect_enabled: bool,
                              cancel_mode: bool = False):
        """Update connect/disconnect button enabled state and styling.

        When cancel_mode is True the disconnect button becomes a Cancel button
        so the user can abort a connection attempt (e.g. during 2FA wait).
        """
        self.connect_button.setEnabled(connect_enabled)
        self.connect_button.setStyleSheet(
            self._connect_active_style if connect_enabled else self._connect_disabled_style
        )

        if cancel_mode:
            self.disconnect_button.setText("Cancel")
            self.disconnect_button.setEnabled(True)
            self.disconnect_button.setStyleSheet(self._cancel_active_style)
        else:
            self.disconnect_button.setText("Disconnect")
            self.disconnect_button.setEnabled(disconnect_enabled)
            self.disconnect_button.setStyleSheet(
                self._disconnect_active_style if disconnect_enabled else self._disconnect_disabled_style
            )

    def _start_connecting_animation(self):
        """Animate the status text while connecting, so the UI looks alive."""
        self._anim_dots = 0
        self._anim_base_text = "Connecting"
        if not hasattr(self, '_anim_timer'):
            self._anim_timer = QTimer(self)
            self._anim_timer.timeout.connect(self._tick_connecting_animation)
        self._anim_timer.start(500)

    def _tick_connecting_animation(self):
        """Cycle dots on the status text: Connecting. → Connecting.. → ..."""
        self._anim_dots = (self._anim_dots + 1) % 4
        dots = "." * (self._anim_dots or 1)
        self.status_text.setText(f"{self._anim_base_text}{dots}")

    def _stop_connecting_animation(self):
        """Stop the connecting animation timer."""
        if hasattr(self, '_anim_timer'):
            self._anim_timer.stop()

    def _on_connect(self):
        """Handle connect button click."""
        if not self.current_profile:
            return

        password = getattr(self.current_profile, '_stored_password', None)
        if not password and self.current_profile.auth_method == "password":
            password, ok = QInputDialog.getText(
                self, "SSH Password",
                f"Password for {self.current_profile.username}@{self.current_profile.host}:",
                QLineEdit.Password
            )
            if not ok or not password:
                self._log_message("Connection cancelled")
                return
            # Remember password for this session and persist to keyring
            self.current_profile._stored_password = password
            self._save_password(self.current_profile, password)

        self._log_message(f"Connecting to {self.current_profile.name}...")
        self.status_light.set_color("yellow")
        self.status_text.setText("Connecting...")
        # Show Cancel button so the user can abort (especially during 2FA)
        self._update_button_states(connect_enabled=False, disconnect_enabled=False,
                                   cancel_mode=True)
        self._start_connecting_animation()

        self.connection_worker = SSHConnectWorker(
            self.ssh_manager, self.current_profile, password=password
        )

        self.connection_thread = QThread()
        self.connection_worker.moveToThread(self.connection_thread)
        self.connection_worker.finished.connect(self.connection_thread.quit)
        self.connection_worker.connected.connect(self._on_ssh_connected)
        self.connection_worker.connection_failed.connect(self._on_connection_failed)
        self.connection_worker.status_message.connect(self._on_connect_status)
        self.connection_worker.waiting_for_2fa.connect(self._on_2fa_waiting)

        self.connection_thread.started.connect(self.connection_worker.run)
        self.connection_thread.start()

    def _on_connect_status(self, message: str):
        """Show connection status messages and update the animation base text."""
        self._log_message(message)
        # Update the animated base text to reflect current phase
        if "2fa" in message.lower() or "waiting" in message.lower():
            self._anim_base_text = "Waiting for 2FA"
        elif "connecting" in message.lower():
            self._anim_base_text = "Connecting"

    def _on_2fa_waiting(self):
        """Update UI when waiting for 2FA approval."""
        self._anim_base_text = "Waiting for 2FA"
        self._log_message("Approve the login on your device...")

    def _on_disconnect(self):
        """Handle disconnect or cancel button click."""
        # If we're in the middle of connecting, cancel the attempt
        if (self.connection_worker and self.connection_thread
                and self.connection_thread.isRunning()):
            self._log_message("Cancelling connection...")
            self._stop_connecting_animation()
            self.connection_worker.cancel()
            self.ssh_manager.disconnect()
            self.connection_thread.quit()
            self.connection_thread.wait(3000)
            self.status_light.set_color("red")
            self.status_text.setText("Connection cancelled")
            self._update_button_states(connect_enabled=True, disconnect_enabled=False)
            self._log_message("Connection cancelled by user")
            return

        if not self.current_profile:
            return

        self._log_message(f"Disconnecting from {self.current_profile.name}...")
        self.status_light.set_color("yellow")
        self.status_text.setText("Disconnecting...")
        self._update_button_states(connect_enabled=False, disconnect_enabled=False)

        # Emit connection_changed(False) BEFORE the SSH transport is torn down
        # so the terminal reader thread is stopped gracefully first.
        self.is_connected = False
        self.connection_changed.emit(False)

        # Store as instance attrs to prevent GC before thread finishes
        self._disconnect_worker = SSHDisconnectWorker(
            self.ssh_manager, self.current_profile.host
        )

        self._disconnect_thread = QThread()
        self._disconnect_worker.moveToThread(self._disconnect_thread)
        self._disconnect_worker.finished.connect(self._disconnect_thread.quit)
        self._disconnect_worker.disconnected.connect(self._on_ssh_disconnected)
        self._disconnect_worker.disconnect_failed.connect(
            lambda msg: self._log_message(f"Disconnect error: {msg}")
        )
        self._disconnect_worker.status_message.connect(self._log_message)

        self._disconnect_thread.started.connect(self._disconnect_worker.run)
        self._disconnect_thread.start()

    def _on_ssh_connected(self):
        """Handle successful SSH connection."""
        self._stop_connecting_animation()
        self.is_connected = True
        self.status_light.set_color("green")
        if self.current_profile:
            self.status_text.setText(f"Connected to {self.current_profile.host}")
            self._log_message(f"Connected to {self.current_profile.host}")
        self._update_button_states(connect_enabled=False, disconnect_enabled=True)
        self.connection_changed.emit(True)

    def _on_ssh_disconnected(self):
        """Handle SSH disconnection."""
        was_connected = self.is_connected
        self.is_connected = False
        self.status_light.set_color("red")
        self.status_text.setText("Not connected")
        self._log_message("Disconnected")
        self._update_button_states(connect_enabled=True, disconnect_enabled=False)
        # Only emit if not already emitted (user-initiated disconnect emits early)
        if was_connected:
            self.connection_changed.emit(False)

    def _on_connection_failed(self, error_message: str):
        """Handle connection failure."""
        self._stop_connecting_animation()
        self.status_light.set_color("red")
        self.status_text.setText("Connection failed")
        self._log_message(f"Failed: {error_message}")
        self._update_button_states(connect_enabled=True, disconnect_enabled=False)

    # ── Logging ──

    def _log_message(self, message: str):
        """Add a message to the connection log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_widget.appendPlainText(f"[{timestamp}] {message}")

    # ── Public API ──

    def get_connection_status(self) -> tuple:
        if self.is_connected and self.current_profile:
            return True, self.current_profile.host
        return False, None

    def disconnect_on_close(self):
        """Disconnect from SSH server before closing."""
        if self.is_connected:
            self._on_disconnect()

    def closeEvent(self, event):
        """Ensure background threads are stopped before widget destruction."""
        for attr in ('connection_thread', '_disconnect_thread'):
            thread = getattr(self, attr, None)
            if thread is not None and thread.isRunning():
                thread.quit()
                if not thread.wait(3000):
                    thread.terminate()
                    thread.wait(1000)
        super().closeEvent(event)
