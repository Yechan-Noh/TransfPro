"""Worker for background SLURM job submission.

This module provides a QObject worker that submits SLURM jobs in a
background thread, handling script upload and job submission.
"""

from PyQt5.QtCore import pyqtSignal

from transfpro.core.slurm_manager import SLURMManager
from .base_worker import BaseWorker


class JobSubmitWorker(BaseWorker):
    """Submit a SLURM job in the background.

    Uploads a job script to the remote system and submits it via SLURM.
    Emits signals to notify the UI of submission progress and results.

    Signals:
        job_submitted: Emitted with job_id when submission succeeds
        submission_failed: Emitted with error message when submission fails
    """

    job_submitted = pyqtSignal(str)  # job_id
    submission_failed = pyqtSignal(str)  # error message

    def __init__(self, slurm_manager: SLURMManager, script_content: str, remote_dir: str):
        """Initialize the job submit worker.

        Args:
            slurm_manager: SLURMManager instance to use for job submission
            script_content: Content of the SLURM job script
            remote_dir: Remote directory where script should be uploaded
        """
        super().__init__()
        self.slurm_manager = slurm_manager
        self.script_content = script_content
        self.remote_dir = remote_dir

    def do_work(self):
        """Upload script and submit job.

        Creates a temporary script file on the remote system and submits
        it as a SLURM job. Emits job_submitted signal with the job ID
        on success, or submission_failed on error.
        """
        try:
            self.status_message.emit("Uploading job script...")
            self.logger.info(f"Preparing to submit job to {self.remote_dir}")

            if self.is_cancelled:
                self.logger.info("Job submission cancelled")
                return

            # Submit job via SLURM manager
            # The manager handles script upload and sbatch execution
            self.status_message.emit("Submitting job to SLURM...")
            job_id = self.slurm_manager.submit_job(self.script_content, self.remote_dir)

            if self.is_cancelled:
                self.logger.info("Job submission cancelled")
                return

            if job_id:
                self.logger.info(f"Job submitted successfully with ID: {job_id}")
                self.job_submitted.emit(job_id)
                self.status_message.emit(f"Job {job_id} submitted successfully!")
            else:
                error_msg = "Job submission returned empty job ID"
                self.logger.error(error_msg)
                self.submission_failed.emit(error_msg)

        except Exception as e:
            error_msg = f"Job submission failed: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.submission_failed.emit(error_msg)
