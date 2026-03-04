"""Cluster information dialog — shows partitions, storage usage, and
available GROMACS modules on the connected cluster."""

import logging
from typing import List, Optional
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QTableWidget, QTableWidgetItem, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QMessageBox, QHeaderView, QProgressBar
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor

logger = logging.getLogger(__name__)


class ClusterInfoFetchWorker(QThread):
    """Worker thread to fetch cluster information."""

    partitions_fetched = pyqtSignal(list)
    storage_fetched = pyqtSignal(list)
    modules_fetched = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, slurm_manager):
        """
        Initialize worker thread.

        Args:
            slurm_manager: SLURMManager instance
        """
        super().__init__()
        self.slurm_manager = slurm_manager

    def run(self):
        """Fetch cluster information in background."""
        try:
            # Fetch partition information
            partitions = self._fetch_partitions()
            if partitions:
                self.partitions_fetched.emit(partitions)

            # Fetch storage information
            storage = self._fetch_storage()
            if storage:
                self.storage_fetched.emit(storage)

            # Fetch available modules
            modules = self._fetch_modules()
            if modules:
                self.modules_fetched.emit(modules)

        except Exception as e:
            logger.error(f"Error fetching cluster info: {e}")
            self.error_occurred.emit(f"Failed to fetch cluster information: {str(e)}")
        finally:
            self.finished.emit()

    def _fetch_partitions(self) -> List[dict]:
        """
        Fetch partition information from cluster.

        Returns:
            List of partition dictionaries
        """
        try:
            if hasattr(self.slurm_manager, 'get_partitions'):
                partitions = self.slurm_manager.get_partitions()
                return partitions if partitions else []
        except Exception as e:
            logger.error(f"Error fetching partitions: {e}")

        return []

    def _fetch_storage(self) -> List[dict]:
        """
        Fetch storage usage information.

        Returns:
            List of storage dictionaries
        """
        try:
            if hasattr(self.slurm_manager, 'get_storage_info'):
                storage = self.slurm_manager.get_storage_info()
                return storage if storage else []
        except Exception as e:
            logger.error(f"Error fetching storage info: {e}")

        # Return mock data for demonstration
        return [
            {
                'path': '/home',
                'used_gb': 250.5,
                'quota_gb': 500.0,
                'usage_percent': 50.1
            },
            {
                'path': '/scratch',
                'used_gb': 1200.0,
                'quota_gb': 2000.0,
                'usage_percent': 60.0
            }
        ]

    def _fetch_modules(self) -> List[str]:
        """
        Fetch available GROMACS modules.

        Returns:
            List of module names
        """
        try:
            if hasattr(self.slurm_manager, 'get_modules'):
                modules = self.slurm_manager.get_modules(pattern="gromacs")
                return modules if modules else self._get_default_modules()
        except Exception as e:
            logger.error(f"Error fetching modules: {e}")

        return self._get_default_modules()

    def _get_default_modules(self) -> List[str]:
        """Get default GROMACS modules for demonstration."""
        return [
            "gromacs/2021.4",
            "gromacs/2021.6",
            "gromacs/2022.2",
            "gromacs/2023.1",
            "gromacs/2024.1"
        ]


class ClusterInfoDialog(QDialog):
    """
    Cluster information viewer dialog.

    Displays detailed information about:
    - Available partitions and their status
    - Storage usage and quotas
    - Available software modules (particularly GROMACS)
    """

    def __init__(self, slurm_manager, parent=None):
        """
        Initialize cluster info dialog.

        Args:
            slurm_manager: SLURMManager instance
            parent: Parent widget
        """
        super().__init__(parent)
        self.slurm_manager = slurm_manager
        self.setWindowTitle("Cluster Information")
        self.setMinimumSize(800, 600)
        self.setModal(True)

        self._setup_ui()
        self._fetch_data()

    def _setup_ui(self):
        """Setup dialog user interface."""
        main_layout = QVBoxLayout()

        # Tab widget for different information categories
        self.tab_widget = QTabWidget()

        # Partitions tab
        self.partitions_tab = self._create_partitions_tab()
        self.tab_widget.addTab(self.partitions_tab, "Partitions")

        # Storage tab
        self.storage_tab = self._create_storage_tab()
        self.tab_widget.addTab(self.storage_tab, "Storage")

        # Modules tab
        self.modules_tab = self._create_modules_tab()
        self.tab_widget.addTab(self.modules_tab, "Modules")

        main_layout.addWidget(self.tab_widget)

        # Button bar
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._fetch_data)
        button_layout.addWidget(refresh_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)

    def _create_partitions_tab(self) -> QWidget:
        """Create partitions information tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        # Partitions table
        self.partitions_table = QTableWidget()
        self.partitions_table.setColumnCount(6)
        self.partitions_table.setHorizontalHeaderLabels([
            "Name",
            "State",
            "Available / Total Nodes",
            "CPUs",
            "Max Time",
            "Default"
        ])

        # Set column widths
        header = self.partitions_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)

        self.partitions_table.setAlternatingRowColors(True)
        layout.addWidget(self.partitions_table)

        widget.setLayout(layout)
        return widget

    def _create_storage_tab(self) -> QWidget:
        """Create storage information tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        # Storage table
        self.storage_table = QTableWidget()
        self.storage_table.setColumnCount(5)
        self.storage_table.setHorizontalHeaderLabels([
            "Path",
            "Used (GB)",
            "Quota (GB)",
            "Usage %",
            "Status"
        ])

        # Set column widths
        header = self.storage_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)

        self.storage_table.setAlternatingRowColors(True)
        layout.addWidget(self.storage_table)

        widget.setLayout(layout)
        return widget

    def _create_modules_tab(self) -> QWidget:
        """Create modules information tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        # Info label
        info_label = QLabel(
            "Available GROMACS modules on this cluster:"
        )
        layout.addWidget(info_label)

        # Modules list
        self.modules_list = QListWidget()
        layout.addWidget(self.modules_list)

        widget.setLayout(layout)
        return widget

    def _fetch_data(self):
        """Start background thread to fetch cluster data."""
        self.worker = ClusterInfoFetchWorker(self.slurm_manager)
        self.worker.partitions_fetched.connect(self._on_partitions_fetched)
        self.worker.storage_fetched.connect(self._on_storage_fetched)
        self.worker.modules_fetched.connect(self._on_modules_fetched)
        self.worker.error_occurred.connect(self._on_fetch_error)
        self.worker.finished.connect(self._on_fetch_finished)
        self.worker.start()

    def _on_partitions_fetched(self, partitions: list):
        """Handle fetched partition data.

        Accepts either dicts or dataclass objects (PartitionInfo) so the
        display works regardless of which backend provides the data.
        """
        def _get(obj, key, default=None):
            """Retrieve a value from a dict or dataclass attribute."""
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        try:
            self.partitions_table.setRowCount(0)

            for partition in partitions:
                row = self.partitions_table.rowCount()
                self.partitions_table.insertRow(row)

                # Name
                name_item = QTableWidgetItem(str(_get(partition, 'name', 'N/A')))
                self.partitions_table.setItem(row, 0, name_item)

                # State
                state = str(_get(partition, 'state', 'unknown'))
                state_item = QTableWidgetItem(state)
                state_color = QColor("#00cc00") if state == "up" else QColor("#ed8796")
                state_item.setForeground(state_color)
                self.partitions_table.setItem(row, 1, state_item)

                # Available / Total Nodes — handle both naming conventions
                avail_nodes = (
                    _get(partition, 'available_nodes')
                    or _get(partition, 'idle_nodes', 0)
                )
                total_nodes = _get(partition, 'total_nodes', 0)
                nodes_item = QTableWidgetItem(f"{avail_nodes} / {total_nodes}")
                self.partitions_table.setItem(row, 2, nodes_item)

                # CPUs — handle both naming conventions
                cpus = (
                    _get(partition, 'total_cpus')
                    or _get(partition, 'cpus_per_node', 0)
                )
                cpus_item = QTableWidgetItem(str(cpus))
                self.partitions_table.setItem(row, 3, cpus_item)

                # Max Time
                max_time_item = QTableWidgetItem(
                    str(_get(partition, 'max_time', 'N/A'))
                )
                self.partitions_table.setItem(row, 4, max_time_item)

                # Default
                is_default = _get(partition, 'default', False)
                default_item = QTableWidgetItem("Yes" if is_default else "")
                default_item.setTextAlignment(Qt.AlignCenter)
                self.partitions_table.setItem(row, 5, default_item)

        except Exception as e:
            logger.error(f"Error displaying partitions: {e}")

    def _on_storage_fetched(self, storage: List[dict]):
        """Handle fetched storage data."""
        try:
            self.storage_table.setRowCount(0)

            for store in storage:
                row = self.storage_table.rowCount()
                self.storage_table.insertRow(row)

                # Path
                path_item = QTableWidgetItem(store.get('path', 'N/A'))
                self.storage_table.setItem(row, 0, path_item)

                # Used (GB)
                used_item = QTableWidgetItem(
                    f"{store.get('used_gb', 0):.2f}"
                )
                self.storage_table.setItem(row, 1, used_item)

                # Quota (GB)
                quota_item = QTableWidgetItem(
                    f"{store.get('quota_gb', 0):.2f}"
                )
                self.storage_table.setItem(row, 2, quota_item)

                # Usage %
                usage_percent = store.get('usage_percent', 0)
                usage_item = QTableWidgetItem(f"{usage_percent:.1f}%")

                # Color code based on usage
                if usage_percent > 90:
                    usage_item.setForeground(QColor("#ed8796"))  # Red
                elif usage_percent > 70:
                    usage_item.setForeground(QColor("#eed49f"))  # Orange
                else:
                    usage_item.setForeground(QColor("#a6da95"))  # Green

                self.storage_table.setItem(row, 3, usage_item)

                # Status
                if usage_percent > 90:
                    status = "Critical"
                    status_color = QColor("#ed8796")
                elif usage_percent > 70:
                    status = "Warning"
                    status_color = QColor("#eed49f")
                else:
                    status = "OK"
                    status_color = QColor("#a6da95")

                status_item = QTableWidgetItem(status)
                status_item.setForeground(status_color)
                self.storage_table.setItem(row, 4, status_item)

        except Exception as e:
            logger.error(f"Error displaying storage info: {e}")

    def _on_modules_fetched(self, modules: List[str]):
        """Handle fetched modules data."""
        try:
            self.modules_list.clear()

            for module in modules:
                item = QListWidgetItem(module)
                self.modules_list.addItem(item)

        except Exception as e:
            logger.error(f"Error displaying modules: {e}")

    def _on_fetch_error(self, error_msg: str):
        """Handle fetch error."""
        logger.error(f"Cluster info fetch error: {error_msg}")
        QMessageBox.warning(self, "Error", error_msg)

    def _on_fetch_finished(self):
        """Handle fetch completion."""
        logger.info("Cluster information fetched")
