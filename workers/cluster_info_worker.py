"""Worker for fetching cluster information.

This module provides a QObject worker that gathers cluster configuration
information including available partitions, modules, and storage details.
"""

from typing import List
from PyQt5.QtCore import pyqtSignal

from transfpro.core.slurm_manager import SLURMManager
from transfpro.models.dashboard import PartitionInfo, StorageInfo
from .base_worker import BaseWorker


class ClusterInfoWorker(BaseWorker):
    """Fetch cluster information (partitions, quotas, modules).

    Gathers static and semi-static cluster information including partition
    details, available software modules, and storage quotas. This worker
    is typically run once at startup and periodically after that.

    Signals:
        partitions_updated: Emitted with List[PartitionInfo]
        modules_updated: Emitted with List[str] - module names
        storage_updated: Emitted with List[StorageInfo]
    """

    partitions_updated = pyqtSignal(list)  # List[PartitionInfo]
    modules_updated = pyqtSignal(list)  # List[str]
    storage_updated = pyqtSignal(list)  # List[StorageInfo]

    def __init__(self, slurm_manager: SLURMManager):
        """Initialize the cluster info worker.

        Args:
            slurm_manager: SLURMManager instance for querying cluster info
        """
        super().__init__()
        self.slurm_manager = slurm_manager

    def do_work(self):
        """Fetch all cluster information.

        Retrieves partition information, available modules, and storage
        quotas. Emits separate signals for each type of information.
        """
        try:
            self.status_message.emit("Fetching cluster information...")
            self.logger.info("Starting cluster information gathering")

            # Step 1: Get partition information
            self.logger.debug("Fetching partition information")
            try:
                partitions = self._fetch_partitions()
                if self.is_cancelled:
                    return
                self.partitions_updated.emit(partitions)
                self.logger.info(f"Retrieved {len(partitions)} partitions")
            except Exception as e:
                self.logger.error(f"Failed to fetch partitions: {e}")
                self.partitions_updated.emit([])

            if self.is_cancelled:
                return

            # Step 2: Get available GROMACS modules
            self.logger.debug("Fetching available GROMACS modules")
            try:
                modules = self._fetch_gromacs_modules()
                if self.is_cancelled:
                    return
                self.modules_updated.emit(modules)
                self.logger.info(f"Retrieved {len(modules)} GROMACS modules")
            except Exception as e:
                self.logger.error(f"Failed to fetch modules: {e}")
                self.modules_updated.emit([])

            if self.is_cancelled:
                return

            # Step 3: Get storage information
            self.logger.debug("Fetching storage quota information")
            try:
                storage = self._fetch_storage_info()
                if self.is_cancelled:
                    return
                self.storage_updated.emit(storage)
                self.logger.info(f"Retrieved {len(storage)} storage locations")
            except Exception as e:
                self.logger.error(f"Failed to fetch storage info: {e}")
                self.storage_updated.emit([])

            self.status_message.emit("Cluster information updated")

        except Exception as e:
            error_msg = f"Failed to fetch cluster information: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            raise

    def _fetch_partitions(self) -> List[PartitionInfo]:
        """Fetch partition information from SLURM.

        Returns:
            List of PartitionInfo objects
        """
        try:
            partitions = self.slurm_manager.get_partitions()
            return partitions
        except Exception as e:
            self.logger.error(f"Error fetching partitions: {e}", exc_info=True)
            return []

    def _fetch_gromacs_modules(self) -> List[str]:
        """Fetch available GROMACS modules.

        Executes module avail to get list of available GROMACS modules.

        Returns:
            List of GROMACS module names
        """
        try:
            # Try to get GROMACS modules
            stdout, stderr, code = self.slurm_manager.ssh.execute_command(
                "module avail 2>&1 | grep -i gromacs | awk '{print $1}'"
            )

            if code == 0 and stdout:
                modules = [
                    m.strip() for m in stdout.strip().split('\n')
                    if m.strip() and not m.startswith('-')
                ]
                return modules
            else:
                self.logger.warning(
                    "Failed to retrieve GROMACS modules or none available"
                )
                return []

        except Exception as e:
            self.logger.error(f"Error fetching GROMACS modules: {e}")
            return []

    def _fetch_storage_info(self) -> List[StorageInfo]:
        """Fetch storage quota and usage information.

        Queries quota information for common storage locations.

        Returns:
            List of StorageInfo objects
        """
        try:
            # Get storage info from SLURM manager
            storage_list = self.slurm_manager.get_disk_usage()
            return storage_list
        except Exception as e:
            self.logger.error(f"Error fetching storage info: {e}")
            return []
