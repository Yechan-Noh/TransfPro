"""Worker for periodic job list queries.

This module provides a QObject worker that periodically queries SLURM
for updated job information in a background thread.
"""

from typing import List
from PyQt5.QtCore import pyqtSignal

from transfpro.core.slurm_manager import SLURMManager
from transfpro.models.job import JobInfo
from .base_worker import BaseWorker


class JobQueryWorker(BaseWorker):
    """Periodically queries SLURM for job updates.

    Fetches the current list of jobs from the SLURM scheduler and emits
    a signal with the updated job list. This worker is typically used for
    periodic refreshes of the job view.

    Signals:
        jobs_updated: Emitted with List[JobInfo] containing current jobs
    """

    jobs_updated = pyqtSignal(list)  # List[JobInfo]

    def __init__(self, slurm_manager: SLURMManager, user: str = None):
        """Initialize the job query worker.

        Args:
            slurm_manager: SLURMManager instance to use for querying jobs
            user: Optional username to filter jobs. If None, queries all jobs.
        """
        super().__init__()
        self.slurm_manager = slurm_manager
        self.user = user

    def do_work(self):
        """Fetch current SLURM jobs.

        Queries the SLURM scheduler for job information and emits the
        jobs_updated signal with the results.
        """
        try:
            self.status_message.emit("Querying SLURM for job updates...")
            self.logger.info(
                f"Fetching jobs from SLURM (user={self.user or 'all'})"
            )

            # Fetch jobs from SLURM
            jobs = self.slurm_manager.get_jobs(user=self.user)

            if self.is_cancelled:
                self.logger.info("Job query cancelled")
                return

            self.logger.info(f"Retrieved {len(jobs)} jobs from SLURM")
            self.jobs_updated.emit(jobs)
            self.status_message.emit(f"Retrieved {len(jobs)} jobs")

        except Exception as e:
            error_msg = f"Failed to query jobs: {str(e)}"
            self.logger.error(error_msg)
            # Emit empty list on error — BaseWorker.run() handles error signal
            self.jobs_updated.emit([])
