"""
Connection Selector widget — embeddable cluster/local picker with icon cards.

Displayed inside each FileBrowserPane. The user picks "Local" or a saved
cluster profile.  Selecting Local immediately emits `local_selected`.
Selecting a cluster triggers an SSH connection flow and emits
`cluster_connected` on success.
"""

import logging
from typing import Optional, List
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGridLayout, QScrollArea, QSizePolicy, QInputDialog,
    QLineEdit, QMessageBox, QDialog, QApplication
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QSize, QEvent, QTimer
from PyQt5.QtGui import QFont, QPixmap, QPainter, QIcon, QColor, QLinearGradient

from transfpro.models.connection import ConnectionProfile
from transfpro.core.ssh_manager import SSHManager
from transfpro.core.sftp_manager import SFTPManager
from transfpro.core.database import Database
from transfpro.workers.ssh_connect_worker import SSHConnectWorker, SSHDisconnectWorker
from transfpro.ui.dialogs.connection_dialog import ConnectionDialog

logger = logging.getLogger(__name__)


class ConnectionSelector(QWidget):
    """Embeddable connection picker: Local + cluster profile cards."""

    # Signals
    local_selected = pyqtSignal()
    cluster_connected = pyqtSignal(object, object, object)  # ssh_mgr, sftp_mgr, profile
    disconnected = pyqtSignal()
    profiles_changed = pyqtSignal()  # emitted when profiles are added/edited/deleted

    # ── Cluster card style constants ──

    _CARD_STYLE = """
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {bg}, stop:1 {pressed_bg});
            border: 1px solid {border};
            border-radius: 12px;
            padding: 10px 12px;
            min-height: 43px;
            min-width: 120px;
            text-align: left;
            font-size: 12px;
            color: #cad3f5;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {hover_bg}, stop:1 {bg});
            border-color: {hover_border};
        }}
        QPushButton:pressed {{
            background: {pressed_bg};
        }}
    """

    _CARD_SELECTED_STYLE = """
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {bg}, stop:1 rgba(30, 32, 48, 0.6));
            border: 2px solid {border};
            border-radius: 12px;
            padding: 10px 12px;
            min-height: 43px;
            min-width: 120px;
            text-align: left;
            font-size: 12px;
            color: #cad3f5;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {hover_bg}, stop:1 {bg});
            border-color: {hover_border};
        }}
    """

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

    # Local card colors
    _LOCAL_COLORS = {
        'icon_bg': '#8aadf4', 'icon_fg': '#1e2030',
        'bg': 'rgba(138, 173, 244, 0.06)', 'border': 'rgba(138, 173, 244, 0.15)',
        'hover_bg': 'rgba(138, 173, 244, 0.12)', 'hover_border': 'rgba(138, 173, 244, 0.4)',
        'pressed_bg': 'rgba(138, 173, 244, 0.18)',
        'sel_bg': 'rgba(138, 173, 244, 0.15)', 'sel_border': '#8aadf4',
        'sel_hover_bg': 'rgba(138, 173, 244, 0.2)', 'sel_hover_border': '#8aadf4',
    }

    _KEYRING_SERVICE = "TransfPro"

    _icon_fonts = {}

    def __init__(self, database: Database, parent=None):
        super().__init__(parent)
        self.database = database
        self.profiles: List[ConnectionProfile] = []
        self._selected_card_index = -1  # -1 = none, 0 = local, 1+ = clusters
        self._card_buttons = []  # list of (btn, colors_dict)

        # Connection state
        self.ssh_manager: Optional[SSHManager] = None
        self.sftp_manager: Optional[SFTPManager] = None
        self.connected_profile: Optional[ConnectionProfile] = None
        self.is_connected = False
        self._connection_thread: Optional[QThread] = None
        self._connection_worker: Optional[SSHConnectWorker] = None
        self._disconnect_thread: Optional[QThread] = None
        self._disconnect_worker: Optional[SSHDisconnectWorker] = None

        # Status label
        self._status_text = ""

        self._setup_ui()
        self._load_profiles()

    # ── UI ──

    # ── Action button style ──
    _ACTION_BTN_STYLE = """
        QPushButton {{
            background: {bg};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 7px 16px;
            font-size: 12px;
            font-weight: 600;
            color: {fg};
        }}
        QPushButton:hover {{
            background: {hover_bg};
            border-color: {hover_border};
        }}
        QPushButton:pressed {{
            background: {pressed};
        }}
        QPushButton:disabled {{
            background: rgba(30, 32, 48, 0.4);
            border-color: rgba(73, 77, 100, 0.3);
            color: rgba(128, 135, 162, 0.5);
        }}
    """

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 28, 24, 20)
        layout.setSpacing(0)

        # ── Header section ──
        header_container = QWidget()
        header_lay = QVBoxLayout(header_container)
        header_lay.setContentsMargins(0, 0, 0, 0)
        header_lay.setSpacing(4)

        # Icon + title row
        title_row = QHBoxLayout()
        title_row.setAlignment(Qt.AlignCenter)

        # Small decorative icon
        title_icon_pixmap = self._make_cluster_icon("⇋", "#8aadf4", "#1e2030", size=28)
        title_icon = QLabel()
        title_icon.setPixmap(title_icon_pixmap)
        title_icon.setFixedSize(28, 28)
        title_row.addWidget(title_icon)
        title_row.addSpacing(8)

        header = QLabel("Select Connection")
        header_font = QFont(header.font())
        header_font.setPointSize(header_font.pointSize() + 4)
        header_font.setWeight(QFont.Bold)
        header.setFont(header_font)
        header.setStyleSheet("color: #cad3f5;")
        title_row.addWidget(header)
        header_lay.addLayout(title_row)

        # Subtitle
        subtitle = QLabel("Choose a local or remote destination")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #6e738d; font-size: 11px; padding-bottom: 4px;")
        header_lay.addWidget(subtitle)

        layout.addWidget(header_container)
        layout.addSpacing(12)

        # ── Status label (connecting animation, errors) ──
        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setStyleSheet("""
            QLabel {
                color: #eed49f;
                font-size: 12px;
                font-weight: 500;
                padding: 6px 12px;
                background: rgba(238, 212, 159, 0.08);
                border: 1px solid rgba(238, 212, 159, 0.15);
                border-radius: 8px;
            }
        """)
        self._status_label.setWordWrap(True)
        self._status_label.setMinimumHeight(0)
        self._status_label.setMaximumHeight(0)  # hidden by default

        # Status row: status label + cancel button side by side
        self._status_row = QHBoxLayout()
        self._status_row.setContentsMargins(0, 0, 0, 0)
        self._status_row.setSpacing(8)
        self._status_row.addWidget(self._status_label, 1)
        # Cancel button placeholder — created later in _setup_ui, added here
        self._cancel_button_placeholder = QWidget()  # replaced below
        self._status_row.addWidget(self._cancel_button_placeholder)
        layout.addLayout(self._status_row)

        # ── Divider ──
        divider = QWidget()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: rgba(73, 77, 100, 0.3);")
        layout.addSpacing(6)
        layout.addWidget(divider)
        layout.addSpacing(14)

        # ── Scrollable grid area ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: rgba(30, 32, 48, 0.3);
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(138, 173, 244, 0.3);
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(138, 173, 244, 0.5);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(10)
        self._grid_layout.setContentsMargins(4, 4, 4, 4)
        self._grid_layout.setColumnStretch(0, 1)
        self._grid_layout.setColumnStretch(1, 1)

        scroll.setWidget(self._grid_container)
        layout.addWidget(scroll, 1)

        layout.addSpacing(10)

        # ── Action buttons with styled appearance ──
        self.new_button = QPushButton("＋  New Connection")
        self.new_button.setToolTip("Create a new connection profile")
        self.new_button.setCursor(Qt.PointingHandCursor)
        self.new_button.setStyleSheet(self._ACTION_BTN_STYLE.format(
            bg='rgba(138, 173, 244, 0.12)', border='rgba(138, 173, 244, 0.25)',
            fg='#8aadf4', hover_bg='rgba(138, 173, 244, 0.2)',
            hover_border='rgba(138, 173, 244, 0.5)', pressed='rgba(138, 173, 244, 0.28)'
        ))
        self.new_button.clicked.connect(self._on_new_connection)

        self.edit_button = QPushButton("Edit")
        self.edit_button.setToolTip("Edit selected profile")
        self.edit_button.setEnabled(False)
        self.edit_button.setCursor(Qt.PointingHandCursor)
        self.edit_button.setStyleSheet(self._ACTION_BTN_STYLE.format(
            bg='rgba(166, 218, 149, 0.08)', border='rgba(166, 218, 149, 0.2)',
            fg='#a6da95', hover_bg='rgba(166, 218, 149, 0.15)',
            hover_border='rgba(166, 218, 149, 0.4)', pressed='rgba(166, 218, 149, 0.22)'
        ))
        self.edit_button.clicked.connect(self._on_edit_connection)

        self.delete_button = QPushButton("Delete")
        self.delete_button.setObjectName("dangerButton")
        self.delete_button.setToolTip("Delete selected profile")
        self.delete_button.setEnabled(False)
        self.delete_button.setCursor(Qt.PointingHandCursor)
        self.delete_button.setStyleSheet(self._ACTION_BTN_STYLE.format(
            bg='rgba(237, 135, 150, 0.08)', border='rgba(237, 135, 150, 0.2)',
            fg='#ed8796', hover_bg='rgba(237, 135, 150, 0.15)',
            hover_border='rgba(237, 135, 150, 0.4)', pressed='rgba(237, 135, 150, 0.22)'
        ))
        self.delete_button.clicked.connect(self._on_delete_connection)

        # Cancel button (shown during connection) — compact, in status row
        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.setStyleSheet(self._ACTION_BTN_STYLE.format(
            bg='rgba(238, 212, 159, 0.10)', border='rgba(238, 212, 159, 0.25)',
            fg='#eed49f', hover_bg='rgba(238, 212, 159, 0.18)',
            hover_border='rgba(238, 212, 159, 0.5)', pressed='rgba(238, 212, 159, 0.25)'
        ))
        self._cancel_button.setCursor(Qt.PointingHandCursor)
        self._cancel_button.clicked.connect(self._on_cancel_connect)
        self._cancel_button.hide()
        # Replace placeholder in the status row
        self._status_row.replaceWidget(self._cancel_button_placeholder, self._cancel_button)
        self._cancel_button_placeholder.deleteLater()

        self.setLayout(layout)

    # ── Icon generation ──

    def _make_cluster_icon(self, initials: str, bg_color: str, fg_color: str,
                           size: int = 40) -> QPixmap:
        """Create a rounded-rect icon with initials for a cluster card."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        # Subtle gradient on icon background
        grad = QLinearGradient(0, 0, 0, size)
        base = QColor(bg_color)
        grad.setColorAt(0.0, base.lighter(115))
        grad.setColorAt(1.0, base)
        painter.setBrush(grad)
        painter.setPen(Qt.NoPen)
        radius = int(size * 0.25)
        painter.drawRoundedRect(0, 0, size, size, radius, radius)
        painter.setPen(QColor(fg_color))
        pixel_size = int(size * 0.40)
        if pixel_size not in self._icon_fonts:
            f = QFont()
            f.setPixelSize(pixel_size)
            f.setWeight(QFont.Black)
            self._icon_fonts[pixel_size] = f
        painter.setFont(self._icon_fonts[pixel_size])
        painter.drawText(pixmap.rect(), Qt.AlignCenter, initials)
        painter.end()
        return pixmap

    # ── Card grid ──

    def _rebuild_card_grid(self):
        """Rebuild the grid with Local card + cluster cards + action buttons."""
        # Reparent action buttons to survive grid clear
        self.new_button.setParent(self)
        self.edit_button.setParent(self)
        self.delete_button.setParent(self)
        self.new_button.hide()
        self.edit_button.hide()
        self.delete_button.hide()

        # Clear grid
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._card_buttons.clear()

        cols = 2
        icon_size = 40

        # ── Section label ──
        section_label = QLabel("CONNECTIONS")
        section_label.setStyleSheet("""
            color: #6e738d;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.5px;
            padding: 0 2px 4px 2px;
        """)
        self._grid_layout.addWidget(section_label, 0, 0, 1, cols)

        # ── LOCAL card (always index 0) ──
        local_icon = self._make_cluster_icon(
            "LC", self._LOCAL_COLORS['icon_bg'], self._LOCAL_COLORS['icon_fg'],
            size=icon_size
        )
        local_card = QPushButton()
        local_card.setIcon(QIcon(local_icon))
        local_card.setIconSize(QSize(icon_size, icon_size))
        local_card.setCursor(Qt.PointingHandCursor)
        local_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        local_card.setText("  Local\n  This Computer")
        local_card.setStyleSheet(self._CARD_STYLE.format(**self._LOCAL_COLORS))
        local_card.clicked.connect(lambda: self._on_card_clicked(0))
        local_card.installEventFilter(self)
        local_card.setProperty("card_index", 0)
        self._card_buttons.append((local_card, self._LOCAL_COLORS))
        self._grid_layout.addWidget(local_card, 1, 0)

        # ── Cluster cards ──
        for idx, profile in enumerate(self.profiles):
            card_idx = idx + 1  # offset by 1 for Local card
            row = (card_idx // cols) + 1  # +1 for section label row
            col = card_idx % cols
            colors = self._CARD_COLORS[idx % len(self._CARD_COLORS)]

            words = profile.name.split()
            if len(words) >= 2:
                initials = words[0][0].upper() + words[1][0].upper()
            else:
                initials = profile.name[:2].upper()

            icon_pixmap = self._make_cluster_icon(
                initials, colors['icon_bg'], colors['icon_fg'],
                size=icon_size
            )

            card = QPushButton()
            card.setIcon(QIcon(icon_pixmap))
            card.setIconSize(QSize(icon_size, icon_size))
            card.setCursor(Qt.PointingHandCursor)
            card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            card.setText(f"  {profile.name}\n  {profile.username}@{profile.host}")
            card.setStyleSheet(self._CARD_STYLE.format(**colors))
            card.clicked.connect(lambda checked, ci=card_idx: self._on_card_clicked(ci))
            card.installEventFilter(self)
            card.setProperty("card_index", card_idx)
            self._card_buttons.append((card, colors))
            self._grid_layout.addWidget(card, row, col)

        # ── Action buttons row ──
        total_cards = 1 + len(self.profiles)
        btn_row = (total_cards // cols) + (1 if total_cards % cols != 0 else 0) + 1  # +1 for section label

        # Thin divider before buttons
        btn_divider = QWidget()
        btn_divider.setFixedHeight(1)
        btn_divider.setStyleSheet("background: rgba(73, 77, 100, 0.2);")
        self._grid_layout.addWidget(btn_divider, btn_row, 0, 1, cols)

        btn_container = QWidget()
        btn_lay = QHBoxLayout(btn_container)
        btn_lay.setContentsMargins(0, 6, 0, 0)
        btn_lay.setSpacing(8)
        btn_lay.addWidget(self.new_button)
        btn_lay.addStretch()
        btn_lay.addWidget(self.edit_button)
        btn_lay.addWidget(self.delete_button)
        self.new_button.show()
        self.edit_button.show()
        self.delete_button.show()
        self._grid_layout.addWidget(btn_container, btn_row + 1, 0, 1, cols)

        # Spacer below
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._grid_layout.addWidget(spacer, btn_row + 2, 0, 1, cols)

    def _on_card_clicked(self, index: int):
        """Handle clicking on a card. index 0 = Local, 1+ = cluster."""
        self._selected_card_index = index

        # Update card highlight styles
        for i, (card, colors) in enumerate(self._card_buttons):
            if i == index:
                card.setStyleSheet(self._CARD_SELECTED_STYLE.format(
                    bg=colors.get('sel_bg', colors['bg']),
                    border=colors.get('sel_border', colors['border']),
                    hover_bg=colors.get('sel_hover_bg', colors['hover_bg']),
                    hover_border=colors.get('sel_hover_border', colors['hover_border']),
                ))
            else:
                card.setStyleSheet(self._CARD_STYLE.format(**colors))

        # Enable edit/delete only for cluster cards (not Local)
        self.edit_button.setEnabled(index > 0)
        self.delete_button.setEnabled(index > 0)

    def _on_card_double_clicked(self, index: int):
        """Double-click a card to select/connect."""
        self._on_card_clicked(index)
        if index == 0:
            # Local — emit immediately
            self.local_selected.emit()
        else:
            # Cluster — start SSH connection
            profile_idx = index - 1
            if 0 <= profile_idx < len(self.profiles):
                self._connect_to_cluster(self.profiles[profile_idx])

    def eventFilter(self, obj, event):
        """Catch double-click on cards."""
        if event.type() == QEvent.MouseButtonDblClick:
            idx = obj.property("card_index")
            if idx is not None:
                self._on_card_double_clicked(idx)
                return True
        return super().eventFilter(obj, event)

    # ── Profile CRUD ──

    def _load_profiles(self):
        """Load connection profiles from database."""
        try:
            self.profiles = []
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
            for profile in self.profiles:
                saved_pw = self._load_password(profile)
                if saved_pw:
                    profile._stored_password = saved_pw

            self._rebuild_card_grid()
        except Exception as e:
            logger.error(f"Error loading profiles: {e}")

    def reload_profiles(self):
        """Reload profiles from database (called when another selector changes profiles)."""
        self._load_profiles()

    def _on_new_connection(self):
        """Create a new connection profile."""
        dialog = ConnectionDialog(profile=None, parent=self)
        if dialog.exec() == QDialog.Accepted:
            profile = dialog.get_profile()
            if self.database:
                try:
                    self.database.save_profile(profile)
                except Exception as e:
                    logger.warning(f"Could not save profile to database: {e}")
            self.profiles.append(profile)
            self._rebuild_card_grid()
            self.profiles_changed.emit()

    def _on_edit_connection(self):
        """Edit the selected cluster profile."""
        if self._selected_card_index <= 0:
            return  # Can't edit Local
        profile_idx = self._selected_card_index - 1
        if profile_idx < 0 or profile_idx >= len(self.profiles):
            return

        profile = self.profiles[profile_idx]
        dialog = ConnectionDialog(profile=profile, parent=self)
        if dialog.exec() == QDialog.Accepted:
            updated = dialog.get_profile()
            if self.database:
                try:
                    self.database.save_profile(updated)
                except Exception as e:
                    logger.warning(f"Could not update profile in database: {e}")
            self.profiles[profile_idx] = updated
            self._rebuild_card_grid()
            self.profiles_changed.emit()

    def _on_delete_connection(self):
        """Delete the selected cluster profile."""
        if self._selected_card_index <= 0:
            return
        profile_idx = self._selected_card_index - 1
        if profile_idx < 0 or profile_idx >= len(self.profiles):
            return

        profile = self.profiles[profile_idx]
        reply = QMessageBox.warning(
            self, "Delete Connection",
            f"Delete '{profile.name}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._delete_password(profile)
            if self.database:
                try:
                    self.database.delete_profile(profile.id)
                except Exception as e:
                    logger.warning(f"Could not delete profile from database: {e}")
            self.profiles = [p for p in self.profiles if p.id != profile.id]
            self._selected_card_index = -1
            self._rebuild_card_grid()
            self.profiles_changed.emit()

    # ── SSH Connection ──

    def _show_status(self, text: str, style: str = "info"):
        """Show the status label with text and style (info, warning, error, success)."""
        color_map = {
            "info": ("#8aadf4", "rgba(138, 173, 244, 0.08)", "rgba(138, 173, 244, 0.15)"),
            "warning": ("#eed49f", "rgba(238, 212, 159, 0.08)", "rgba(238, 212, 159, 0.15)"),
            "error": ("#ed8796", "rgba(237, 135, 150, 0.08)", "rgba(237, 135, 150, 0.15)"),
            "success": ("#a6da95", "rgba(166, 218, 149, 0.08)", "rgba(166, 218, 149, 0.15)"),
        }
        fg, bg, bdr = color_map.get(style, color_map["info"])
        self._status_label.setStyleSheet(f"""
            QLabel {{
                color: {fg};
                font-size: 12px;
                font-weight: 500;
                padding: 6px 12px;
                background: {bg};
                border: 1px solid {bdr};
                border-radius: 8px;
            }}
        """)
        self._status_label.setText(text)
        self._status_label.setMaximumHeight(50)
        self._status_label.setMinimumHeight(28)

    def _hide_status(self):
        """Hide the status label."""
        self._status_label.setText("")
        self._status_label.setMaximumHeight(0)
        self._status_label.setMinimumHeight(0)

    def _connect_to_cluster(self, profile: ConnectionProfile):
        """Start SSH connection to a cluster profile."""
        password = getattr(profile, '_stored_password', None)
        if not password and profile.auth_method == "password":
            password, ok = QInputDialog.getText(
                self, "SSH Password",
                f"Password for {profile.username}@{profile.host}:",
                QLineEdit.Password
            )
            if not ok or not password:
                return
            profile._stored_password = password
            self._save_password(profile, password)

        self._show_status(f"Connecting to {profile.name}...", "info")
        self._cancel_button.show()
        self._start_connecting_animation()

        # Create a fresh SSH manager for this pane
        self.ssh_manager = SSHManager()
        self.sftp_manager = SFTPManager(self.ssh_manager)
        self.connected_profile = profile

        self._connection_worker = SSHConnectWorker(
            self.ssh_manager, profile, password=password
        )
        self._connection_thread = QThread()
        self._connection_worker.moveToThread(self._connection_thread)
        self._connection_worker.finished.connect(self._connection_thread.quit)
        self._connection_worker.connected.connect(self._on_ssh_connected)
        self._connection_worker.connection_failed.connect(self._on_connection_failed)
        self._connection_worker.status_message.connect(self._on_connect_status)
        self._connection_worker.waiting_for_2fa.connect(self._on_2fa_waiting)
        self._connection_thread.started.connect(self._connection_worker.run)
        self._connection_thread.start()

    def _on_connect_status(self, message: str):
        if "2fa" in message.lower() or "waiting" in message.lower():
            self._anim_base_text = "Waiting for 2FA"
        elif "connecting" in message.lower():
            self._anim_base_text = "Connecting"

    def _on_2fa_waiting(self):
        self._anim_base_text = "Waiting for 2FA"

    def _on_ssh_connected(self):
        """SSH connection succeeded."""
        self._stop_connecting_animation()
        self.is_connected = True
        self._cancel_button.hide()
        self._show_status(f"Connected to {self.connected_profile.name}", "success")
        self.cluster_connected.emit(
            self.ssh_manager, self.sftp_manager, self.connected_profile
        )

    def _on_connection_failed(self, error_message: str):
        self._stop_connecting_animation()
        self._cancel_button.hide()
        self._show_status(f"Failed: {error_message}", "error")
        self.ssh_manager = None
        self.sftp_manager = None
        self.connected_profile = None

    def _on_cancel_connect(self):
        """Cancel an in-progress connection attempt."""
        if self._connection_worker and self._connection_thread and self._connection_thread.isRunning():
            self._connection_worker.cancel()
            if self.ssh_manager:
                self.ssh_manager.disconnect()
            self._connection_thread.quit()
            self._connection_thread.wait(3000)
        self._stop_connecting_animation()
        self._cancel_button.hide()
        self._show_status("Connection cancelled", "warning")
        self.ssh_manager = None
        self.sftp_manager = None
        self.connected_profile = None

    def disconnect_current(self):
        """Disconnect from the currently connected cluster."""
        if not self.is_connected or not self.ssh_manager:
            return
        self.is_connected = False
        hostname = self.connected_profile.host if self.connected_profile else ""

        # Disconnect on background thread
        self._disconnect_worker = SSHDisconnectWorker(self.ssh_manager, hostname)
        self._disconnect_thread = QThread()
        self._disconnect_worker.moveToThread(self._disconnect_thread)
        self._disconnect_worker.finished.connect(self._disconnect_thread.quit)
        self._disconnect_worker.disconnected.connect(self._on_ssh_disconnected)
        self._disconnect_worker.disconnect_failed.connect(
            lambda msg: logger.warning(f"Disconnect error: {msg}")
        )
        self._disconnect_thread.started.connect(self._disconnect_worker.run)
        self._disconnect_thread.start()

        self.disconnected.emit()

    def _on_ssh_disconnected(self):
        self.ssh_manager = None
        self.sftp_manager = None
        self.connected_profile = None
        self._hide_status()

    # ── Connecting animation ──

    def _start_connecting_animation(self):
        self._anim_dots = 0
        self._anim_base_text = "Connecting"
        if not hasattr(self, '_anim_timer'):
            self._anim_timer = QTimer(self)
            self._anim_timer.timeout.connect(self._tick_connecting_animation)
        self._anim_timer.start(500)

    def _tick_connecting_animation(self):
        self._anim_dots = (self._anim_dots + 1) % 4
        dots = "." * (self._anim_dots or 1)
        style = "warning" if "2FA" in self._anim_base_text else "info"
        self._show_status(f"{self._anim_base_text}{dots}", style)

    def _stop_connecting_animation(self):
        if hasattr(self, '_anim_timer'):
            self._anim_timer.stop()

    # ── Password store helpers ──

    @staticmethod
    def _pw_key(profile: ConnectionProfile) -> str:
        return f"{profile.username}@{profile.host}:{profile.port}"

    def _save_password(self, profile: ConnectionProfile, password: str):
        try:
            from transfpro.core.password_store import set_password
            set_password(self._KEYRING_SERVICE, self._pw_key(profile), password)
        except Exception as e:
            logger.warning(f"Could not save password: {e}")

    def _load_password(self, profile: ConnectionProfile) -> Optional[str]:
        try:
            from transfpro.core.password_store import get_password
            return get_password(self._KEYRING_SERVICE, self._pw_key(profile))
        except Exception as e:
            logger.warning(f"Could not load password: {e}")
            return None

    def _delete_password(self, profile: ConnectionProfile):
        try:
            from transfpro.core.password_store import delete_password
            delete_password(self._KEYRING_SERVICE, self._pw_key(profile))
        except Exception as e:
            logger.debug(f"Could not delete password: {e}")

    # ── Cleanup ──

    def cleanup_threads(self):
        """Stop any running threads — called during app shutdown."""
        if hasattr(self, '_anim_timer'):
            self._anim_timer.stop()
        for attr in ('_connection_thread', '_disconnect_thread'):
            thread = getattr(self, attr, None)
            if thread is not None and thread.isRunning():
                thread.quit()
                if not thread.wait(500):
                    thread.terminate()
                    thread.wait(200)
