"""Dialog for creating or editing an SSH connection profile, including
2FA options, key-based auth, and advanced timeout settings."""

import os
import re
from typing import Optional, Tuple
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QSpinBox, QComboBox, QCheckBox, QPushButton,
    QFileDialog, QLabel, QWidget, QMessageBox, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QIntValidator

# RFC 1123 hostname + IPv4/IPv6 validation
_HOSTNAME_RE = re.compile(
    r'^('
    r'([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)*'
    r'[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?'
    r'|'
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'  # IPv4
    r'|'
    r'\[?[0-9a-fA-F:]+\]?'  # IPv6
    r')$'
)

from transfpro.models.connection import ConnectionProfile
from transfpro.core.ssh_manager import SSHManager


class ConnectionDialog(QDialog):
    """Modal dialog for SSH connection profile creation / editing."""

    connection_tested = pyqtSignal(bool, str)

    def __init__(self, profile: Optional[ConnectionProfile] = None, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.ssh_manager = SSHManager()
        self.is_edit_mode = profile is not None
        self._setup_ui()
        if self.is_edit_mode:
            self._load_profile()
        self.setWindowTitle("Edit Connection" if self.is_edit_mode else "New Connection")

    def _setup_ui(self):
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setMaximumWidth(700)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        # Title — uses app font scaled up so it respects the global size setting
        title = QLabel("Edit Connection" if self.is_edit_mode else "New Connection")
        title_font = QFont(title.font())
        title_font.setPointSize(title_font.pointSize() + 6)
        title_font.setWeight(QFont.Black)
        title.setFont(title_font)
        title.setStyleSheet("letter-spacing: 0.3px; padding-bottom: 4px;")
        layout.addWidget(title)

        # ── Server Details Card ──
        server_group = QGroupBox("Server")
        server_form = QFormLayout()
        server_form.setSpacing(12)
        server_form.setHorizontalSpacing(16)
        server_form.setLabelAlignment(Qt.AlignLeft)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., My HPC Cluster")
        self.name_input.setMinimumWidth(260)
        server_form.addRow("Name", self.name_input)

        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("e.g., cluster.example.com")
        server_form.addRow("Host", self.host_input)

        host_port_layout = QHBoxLayout()
        self.port_input = QSpinBox()
        self.port_input.setMinimum(1)
        self.port_input.setMaximum(65535)
        self.port_input.setValue(22)
        self.port_input.setMaximumWidth(100)
        host_port_layout.addWidget(self.port_input)
        host_port_layout.addStretch()
        server_form.addRow("Port", host_port_layout)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("e.g., john.doe")
        server_form.addRow("Username", self.username_input)

        server_group.setLayout(server_form)
        layout.addWidget(server_group)

        # ── Authentication Card ──
        auth_group = QGroupBox("Authentication")
        auth_form = QFormLayout()
        auth_form.setSpacing(12)
        auth_form.setHorizontalSpacing(16)
        auth_form.setLabelAlignment(Qt.AlignLeft)

        self.auth_method_combo = QComboBox()
        self.auth_method_combo.addItems(["Password", "SSH Key"])
        self.auth_method_combo.currentTextChanged.connect(self._on_auth_method_changed)
        auth_form.addRow("Method", self.auth_method_combo)

        # SSH Key row (hidden by default)
        key_layout = QHBoxLayout()
        self.key_path_input = QLineEdit()
        self.key_path_input.setPlaceholderText("~/.ssh/id_rsa")
        self.key_path_input.setReadOnly(True)
        key_layout.addWidget(self.key_path_input)

        self.browse_key_button = QPushButton("Browse")
        self.browse_key_button.clicked.connect(self._on_browse_key)
        self.browse_key_button.setMaximumWidth(90)
        key_layout.addWidget(self.browse_key_button)

        self.key_widget = QWidget()
        self.key_widget.setLayout(key_layout)
        auth_form.addRow("Key File", self.key_widget)
        self.key_widget.setVisible(False)

        self.remember_password_check = QCheckBox("Save password")
        self.remember_password_check.setChecked(False)
        auth_form.addRow("", self.remember_password_check)

        auth_group.setLayout(auth_form)
        layout.addWidget(auth_group)

        # ── 2FA Card ──
        twofa_group = QGroupBox("Two-Factor Authentication")
        twofa_layout = QVBoxLayout()
        twofa_layout.setSpacing(10)

        self.has_2fa_check = QCheckBox("Enable 2FA")
        self.has_2fa_check.setChecked(False)
        self.has_2fa_check.stateChanged.connect(self._on_2fa_toggled)
        twofa_layout.addWidget(self.has_2fa_check)

        twofa_form = QFormLayout()
        twofa_form.setSpacing(10)
        twofa_form.setHorizontalSpacing(16)
        twofa_form.setLabelAlignment(Qt.AlignLeft)

        self.twofa_response_input = QLineEdit()
        self.twofa_response_input.setText("1")
        self.twofa_response_input.setMaximumWidth(80)
        self.twofa_response_input.setToolTip("Response to send (e.g. '1' for Duo push)")
        self.twofa_response_input.setEnabled(False)
        twofa_form.addRow("Response", self.twofa_response_input)

        self.twofa_timeout_input = QSpinBox()
        self.twofa_timeout_input.setMinimum(10)
        self.twofa_timeout_input.setMaximum(120)
        self.twofa_timeout_input.setValue(60)
        self.twofa_timeout_input.setSuffix(" sec")
        self.twofa_timeout_input.setEnabled(False)
        twofa_form.addRow("Timeout", self.twofa_timeout_input)

        twofa_layout.addLayout(twofa_form)
        twofa_group.setLayout(twofa_layout)
        layout.addWidget(twofa_group)

        # ── Advanced Settings Card ──
        adv_group = QGroupBox("Advanced")
        adv_form = QFormLayout()
        adv_form.setSpacing(10)
        adv_form.setHorizontalSpacing(16)
        adv_form.setLabelAlignment(Qt.AlignLeft)

        self.timeout_input = QSpinBox()
        self.timeout_input.setMinimum(5)
        self.timeout_input.setMaximum(60)
        self.timeout_input.setValue(10)
        self.timeout_input.setSuffix(" sec")
        adv_form.addRow("Timeout", self.timeout_input)

        self.auto_reconnect_check = QCheckBox("Auto-reconnect on disconnect")
        self.auto_reconnect_check.setChecked(True)
        adv_form.addRow("", self.auto_reconnect_check)

        self.keepalive_input = QSpinBox()
        self.keepalive_input.setMinimum(10)
        self.keepalive_input.setMaximum(120)
        self.keepalive_input.setValue(30)
        self.keepalive_input.setSuffix(" sec")
        adv_form.addRow("Keepalive", self.keepalive_input)

        adv_group.setLayout(adv_form)
        layout.addWidget(adv_group)

        # ── Action buttons ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        btn_layout.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setMinimumWidth(100)
        self.cancel_button.setCursor(Qt.PointingHandCursor)
        self.cancel_button.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_button)

        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("successButton")
        self.save_button.setMinimumWidth(100)
        self.save_button.setCursor(Qt.PointingHandCursor)
        self.save_button.clicked.connect(self.accept)
        btn_layout.addWidget(self.save_button)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _on_auth_method_changed(self, method: str):
        is_key = method == "SSH Key"
        self.key_widget.setVisible(is_key)
        self.remember_password_check.setEnabled(not is_key)

    def _on_2fa_toggled(self, state):
        enabled = state == Qt.Checked
        self.twofa_response_input.setEnabled(enabled)
        self.twofa_timeout_input.setEnabled(enabled)

    def _on_browse_key(self):
        home = os.path.expanduser("~")
        ssh_dir = os.path.join(home, ".ssh")

        path, _ = QFileDialog.getOpenFileName(
            self, "Select SSH Key",
            ssh_dir if os.path.exists(ssh_dir) else home,
            "SSH Keys (id_rsa id_dsa id_ecdsa id_ed25519);;All Files (*)"
        )
        if path:
            self.key_path_input.setText(path)

    def _load_profile(self):
        """Load profile data into form (edit mode)."""
        if not self.profile:
            return

        self.name_input.setText(self.profile.name)
        self.host_input.setText(self.profile.host)
        self.port_input.setValue(self.profile.port)
        self.username_input.setText(self.profile.username)

        if self.profile.auth_method == "key":
            self.auth_method_combo.setCurrentText("SSH Key")
            if self.profile.key_path:
                self.key_path_input.setText(self.profile.key_path)
        else:
            self.auth_method_combo.setCurrentText("Password")

        self.remember_password_check.setChecked(self.profile.remember_password)
        self.has_2fa_check.setChecked(self.profile.has_2fa)
        self.twofa_response_input.setText(self.profile.two_fa_response)
        self.twofa_timeout_input.setValue(self.profile.two_fa_timeout)
        self.timeout_input.setValue(self.profile.timeout)
        self.auto_reconnect_check.setChecked(self.profile.auto_reconnect)
        self.keepalive_input.setValue(self.profile.keepalive_interval)

    def get_profile(self) -> ConnectionProfile:
        """Build a ConnectionProfile from form inputs."""
        auth_method = "key" if self.auth_method_combo.currentText() == "SSH Key" else "password"

        profile = ConnectionProfile(
            name=self.name_input.text().strip(),
            host=self.host_input.text().strip(),
            port=self.port_input.value(),
            username=self.username_input.text().strip(),
            auth_method=auth_method,
            key_path=self.key_path_input.text().strip() if auth_method == "key" else None,
            has_2fa=self.has_2fa_check.isChecked(),
            two_fa_response=self.twofa_response_input.text().strip(),
            two_fa_timeout=self.twofa_timeout_input.value(),
            remember_password=self.remember_password_check.isChecked(),
            timeout=self.timeout_input.value(),
            auto_reconnect=self.auto_reconnect_check.isChecked(),
            keepalive_interval=self.keepalive_input.value(),
        )

        # Preserve ID for edits (new profiles get auto-generated UUID)
        if self.profile:
            profile.id = self.profile.id

        if self.profile:
            profile.created_at = self.profile.created_at
            profile.last_connected = self.profile.last_connected

        return profile

    def validate(self) -> Tuple[bool, str]:
        """Validate the form."""
        if not self.name_input.text().strip():
            return False, "Profile name is required"
        host = self.host_input.text().strip()
        if not host:
            return False, "Host is required"
        if not _HOSTNAME_RE.match(host):
            return False, "Invalid hostname or IP address"
        if not self.username_input.text().strip():
            return False, "Username is required"
        if self.auth_method_combo.currentText() == "SSH Key":
            if not self.key_path_input.text().strip():
                return False, "SSH key path is required"
            if not os.path.exists(self.key_path_input.text().strip()):
                return False, "SSH key file does not exist"
        return True, ""

    def accept(self):
        """Validate and accept."""
        is_valid, error_msg = self.validate()
        if not is_valid:
            QMessageBox.warning(self, "Validation Error", error_msg)
            return
        super().accept()
