"""
About Dialog for TransfPro Application.

Simple informational dialog displaying application information, version,
description, and credits.
"""

import logging
from datetime import datetime
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QFont, QPixmap, QIcon

from transfpro.config.constants import APP_VERSION, APP_AUTHOR

logger = logging.getLogger(__name__)


class AboutDialog(QDialog):
    """
    About dialog displaying application information.

    Shows application name, version, description, author information,
    and list of used libraries.
    """

    def __init__(self, parent=None):
        """
        Initialize about dialog.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("About TransfPro")
        self.setMinimumSize(500, 500)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self._setup_ui()

    def _setup_ui(self):
        """Setup dialog user interface."""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(15)

        # App icon/logo section
        icon_layout = QHBoxLayout()
        icon_layout.addStretch()

        icon_label = QLabel()
        # Try to load application icon if available
        icon_path = self._get_icon_path()
        if icon_path:
            pixmap = QPixmap(icon_path).scaledToWidth(
                80, Qt.SmoothTransformation
            )
            icon_label.setPixmap(pixmap)
        else:
            # Fallback to generic application icon
            icon = self.style().standardIcon(
                self.style().SP_DialogYesButton
            )
            pixmap = icon.pixmap(QSize(80, 80))
            icon_label.setPixmap(pixmap)

        icon_layout.addWidget(icon_label)
        icon_layout.addStretch()
        main_layout.addLayout(icon_layout)

        # App name (large, bold)
        app_name = QLabel("TransfPro")
        font = QFont()
        font.setPointSize(24)
        font.setBold(True)
        app_name.setFont(font)
        app_name.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(app_name)

        # Version
        version_label = QLabel(f"Version {APP_VERSION}")
        version_font = QFont()
        version_font.setPointSize(12)
        version_label.setFont(version_font)
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setStyleSheet("color: #888888;")
        main_layout.addWidget(version_label)

        # Separator
        separator = QLabel("-" * 50)
        separator.setAlignment(Qt.AlignCenter)
        separator.setStyleSheet("color: #555555;")
        main_layout.addWidget(separator)

        # Description
        description = QLabel(
            "Secure File Transfer & Remote Server Management\n\n"
            "A comprehensive PyQt5-based tool for managing remote servers "
            "and HPC clusters. Features SSH connection management, "
            "SLURM job submission and monitoring, SFTP file transfer, "
            "and real-time terminal access."
        )
        description.setAlignment(Qt.AlignCenter)
        description.setWordWrap(True)
        description.setStyleSheet("line-height: 1.5;")
        main_layout.addWidget(description)

        # Author info
        main_layout.addSpacing(15)
        author_label = QLabel("Author Information")
        author_font = QFont()
        author_font.setBold(True)
        author_label.setFont(author_font)
        main_layout.addWidget(author_label)

        author_info = QLabel(
            "Developed as a versatile tool for remote server management\n"
            "and secure file transfer across SSH/SFTP connections."
        )
        author_info.setWordWrap(True)
        author_info.setStyleSheet("color: #aaaaaa;")
        main_layout.addWidget(author_info)

        # Libraries section
        main_layout.addSpacing(15)
        libraries_label = QLabel("Built with:")
        libraries_font = QFont()
        libraries_font.setBold(True)
        libraries_label.setFont(libraries_font)
        main_layout.addWidget(libraries_label)

        libraries_text = QLabel(
            "• PyQt5 - Graphical User Interface Framework\n"
            "• Paramiko - SSH Protocol Implementation\n"
            "• Matplotlib - Data Visualization and Charting\n"
            "• PyQtGraph - High-Performance Graphics Library\n"
            "• Keyring - Secure Credential Storage\n"
            "• Cryptography - Cryptographic Recipes and Primitives"
        )
        libraries_text.setWordWrap(True)
        libraries_text.setStyleSheet("color: #aaaaaa; margin-left: 10px;")
        main_layout.addWidget(libraries_text)

        # Support / website
        main_layout.addSpacing(10)
        support_label = QLabel(
            'Support: <a href="mailto:support@transfpro.com">support@transfpro.com</a>'
        )
        support_label.setAlignment(Qt.AlignCenter)
        support_label.setOpenExternalLinks(True)
        support_label.setStyleSheet("color: #888888; font-size: 11px;")
        main_layout.addWidget(support_label)

        # License section
        main_layout.addSpacing(10)
        license_label = QLabel(
            "Licensed under the MIT License.\n"
            f"Copyright \u00a9 {datetime.now().year} {APP_AUTHOR}. All rights reserved."
        )
        license_label.setAlignment(Qt.AlignCenter)
        license_label.setWordWrap(True)
        license_label.setStyleSheet("color: #666666; font-size: 10px;")
        main_layout.addWidget(license_label)

        main_layout.addStretch()

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setMaximumWidth(150)
        close_btn.clicked.connect(self.accept)

        close_layout = QHBoxLayout()
        close_layout.addStretch()
        close_layout.addWidget(close_btn)
        close_layout.addStretch()
        main_layout.addLayout(close_layout)

        self.setLayout(main_layout)

    def _get_icon_path(self) -> str:
        """
        Get the path to the application icon.

        Returns:
            Path to icon file, or empty string if not found
        """
        from pathlib import Path

        # Check common locations for application icon
        possible_paths = [
            Path(__file__).parent.parent.parent / "resources" / "transfpro_icon.png",
            Path(__file__).parent.parent / "resources" / "transfpro_icon.png",
            Path(__file__).parent.parent / "resources" / "icons" / "app_icon.png",
        ]

        for path in possible_paths:
            if path.exists():
                return str(path)

        return ""
