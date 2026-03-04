"""
Main Job Manager tab for TransfPro.

This module provides the JobManagerTab widget for job submission and monitoring,
with automatic refresh, detailed job views, and log access.
"""

import logging
from typing import Optional, List
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QPushButton,
    QCheckBox, QSpinBox, QLabel, QSplitter, QTabWidget,
    QFormLayout, QPlainTextEdit, QMessageBox, QDialog, QSizePolicy
)
from PyQt5.QtCore import Qt, QObject, QThread, QTimer, pyqtSignal, pyqtSlot, QSize
from PyQt5.QtGui import QIcon

from transfpro.core.slurm_manager import SLURMManager, JobInfo
from transfpro.core.sftp_manager import SFTPManager
from transfpro.core.database import Database
from transfpro.core.gromacs_parser import GromacsLogParser
from transfpro.workers.job_query_worker import JobQueryWorker
from transfpro.ui.widgets.job_table_widget import JobTableWidget
from transfpro.ui.dialogs.job_submit_dialog import JobSubmitDialog
from transfpro.ui.dialogs.log_viewer_dialog import LogViewerDialog
from transfpro.ui.dialogs.job_template_dialog import JobTemplateDialog

logger = logging.getLogger(__name__)


class CancelJobWorker(QObject):
    """Worker to cancel SLURM jobs in a background thread."""

    finished = pyqtSignal()
    results_ready = pyqtSignal(list, list)  # succeeded_ids, failed_ids

    def __init__(self, ssh_manager, job_ids: List[str]):
        super().__init__()
        self._ssh = ssh_manager
        self._job_ids = job_ids

    @pyqtSlot()
    def run(self):
        """Cancel jobs via scancel and emit results."""
        try:
            # Cancel all jobs in a single scancel call (much faster)
            ids_str = " ".join(self._job_ids)
            command = f"scancel {ids_str}"
            logger.info(f"Executing: {command}")

            stdout, stderr, exit_code = self._ssh.execute_command(command, timeout=10)

            if exit_code == 0:
                self.results_ready.emit(list(self._job_ids), [])
            else:
                # Some may have failed — try individually
                succeeded = []
                failed = []
                for jid in self._job_ids:
                    try:
                        _, err, code = self._ssh.execute_command(
                            f"scancel {jid}", timeout=10
                        )
                        if code == 0:
                            succeeded.append(jid)
                        else:
                            failed.append(jid)
                    except Exception:
                        failed.append(jid)
                self.results_ready.emit(succeeded, failed)
        except Exception as e:
            logger.error(f"Cancel worker error: {e}")
            self.results_ready.emit([], list(self._job_ids))
        finally:
            self.finished.emit()


class JobManagerTab(QWidget):
    """Job submission and monitoring interface."""

    view_log_requested = pyqtSignal(str, str)  # job_id, log_path
    open_directory_requested = pyqtSignal(str)  # remote path

    def __init__(self, slurm_manager: SLURMManager, ssh_manager,
                 sftp_manager: SFTPManager, gromacs_parser: GromacsLogParser,
                 database: Database, parent=None):
        """
        Initialize the Job Manager tab.

        Args:
            slurm_manager: SLURMManager instance
            ssh_manager: SSHManager instance
            sftp_manager: SFTPManager instance
            gromacs_parser: GromacsLogParser instance
            database: Database instance
            parent: Parent widget
        """
        super().__init__(parent)
        self.slurm_manager = slurm_manager
        self.ssh_manager = ssh_manager
        self.sftp_manager = sftp_manager
        self.gromacs_parser = gromacs_parser
        self.database = database

        self.query_thread: Optional[QThread] = None
        self.query_worker: Optional[JobQueryWorker] = None
        self.cancel_thread: Optional[QThread] = None
        self.cancel_worker: Optional[CancelJobWorker] = None
        self.refresh_timer: Optional[QTimer] = None

        self._setup_ui()
        self._setup_connections()
        self._setup_auto_refresh()

    def _setup_ui(self):
        """Set up the UI layout."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)

        # Main content: Horizontal splitter — table (left) + details (right)
        splitter = QSplitter(Qt.Horizontal)

        # Left: Job table (full height)
        self.job_table = JobTableWidget()
        splitter.addWidget(self.job_table)

        # Right: Job details panel
        self.details_panel = self._create_details_panel()
        splitter.addWidget(self.details_panel)

        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, True)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)
        self.setLayout(layout)

    def _create_toolbar(self) -> QToolBar:
        """
        Create the toolbar.

        Returns:
            QToolBar widget
        """
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))

        # Cancel button (supports multi-select)
        cancel_btn = QPushButton("Cancel Job(s)")
        cancel_btn.setStyleSheet(
            "QPushButton { background-color: #F44336; color: white; }"
        )
        cancel_btn.clicked.connect(self.on_cancel_job)
        toolbar.addWidget(cancel_btn)

        toolbar.addSeparator()

        # Resubmit button
        resubmit_btn = QPushButton("Resubmit")
        resubmit_btn.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; }"
        )
        resubmit_btn.setToolTip("Re-run the same sbatch script for the selected job")
        resubmit_btn.clicked.connect(self._on_resubmit_selected)
        toolbar.addWidget(resubmit_btn)

        toolbar.addSeparator()

        # View log button
        log_btn = QPushButton("View Log")
        log_btn.clicked.connect(self.on_view_log)
        toolbar.addWidget(log_btn)

        # Refresh button
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_jobs)
        toolbar.addWidget(self.refresh_btn)

        toolbar.addSeparator()

        # Auto-refresh checkbox
        auto_refresh_check = QCheckBox("Auto-refresh")
        auto_refresh_check.setChecked(True)
        auto_refresh_check.toggled.connect(self._on_auto_refresh_toggled)
        toolbar.addWidget(auto_refresh_check)

        # Refresh interval
        interval_label = QLabel("Interval (s):")
        toolbar.addWidget(interval_label)

        self.refresh_interval_spin = QSpinBox()
        self.refresh_interval_spin.setMinimum(5)
        self.refresh_interval_spin.setMaximum(600)
        self.refresh_interval_spin.setValue(300)
        self.refresh_interval_spin.setMaximumWidth(80)
        self.refresh_interval_spin.valueChanged.connect(self._on_refresh_interval_changed)
        toolbar.addWidget(self.refresh_interval_spin)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        # Template button
        template_btn = QPushButton("Templates")
        template_btn.clicked.connect(self._on_templates_clicked)
        toolbar.addWidget(template_btn)

        return toolbar

    def _create_details_panel(self) -> QWidget:
        """
        Create the job details panel.

        Returns:
            QWidget containing the details panel
        """
        panel = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)

        # Tab widget
        self.details_tabs = QTabWidget()

        # Details tab
        details_widget = QWidget()
        details_form = QFormLayout()

        self.detail_fields = {
            'job_id': QLabel(),
            'name': QLabel(),
            'user': QLabel(),
            'state': QLabel(),
            'queue': QLabel(),
            'nodes': QLabel(),
            'cpus': QLabel(),
            'memory': QLabel(),
            'time_limit': QLabel(),
            'elapsed': QLabel(),
            'start_time': QLabel(),
            'node_list': QLabel(),
            'exit_code': QLabel(),
        }

        for field_name, field_widget in self.detail_fields.items():
            label = field_name.replace('_', ' ').title()
            details_form.addRow(f"{label}:", field_widget)

        details_widget.setLayout(details_form)
        self.details_tabs.addTab(details_widget, "Details")

        # Output tab
        self.output_text = QPlainTextEdit()
        self.output_text.setReadOnly(True)
        self.details_tabs.addTab(self.output_text, "Output")

        # Script tab
        self.script_text = QPlainTextEdit()
        self.script_text.setReadOnly(True)
        self.details_tabs.addTab(self.script_text, "Script")

        layout.addWidget(self.details_tabs)
        panel.setLayout(layout)

        return panel

    def _setup_connections(self):
        """Set up signal/slot connections."""
        self.job_table.job_selected.connect(self.on_job_selected)
        self.job_table.job_double_clicked.connect(self.on_view_log)
        self.job_table.resubmit_requested.connect(self._on_resubmit_job)
        self.job_table.cancel_requested.connect(self._on_cancel_single_job)

    def _on_cancel_single_job(self, job):
        """Handle cancel from right-click context menu (single job)."""
        # Snapshot data before any dialog (auto-refresh could mutate the table)
        jid = job.job_id
        jname = job.name
        jstate = job.state

        if jstate.upper() not in ("RUNNING", "PENDING"):
            QMessageBox.warning(
                self, "Cannot Cancel",
                f"Job {jid} is {jstate} and cannot be cancelled."
            )
            return

        was_running = self.refresh_timer and self.refresh_timer.isActive()
        if was_running:
            self.refresh_timer.stop()

        reply = QMessageBox.question(
            self, "Confirm Cancel",
            f"Cancel job {jid} ({jname})?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if was_running:
            self.refresh_timer.start()

        if reply != QMessageBox.Yes:
            return

        self._launch_cancel([jid])

    def _setup_auto_refresh(self):
        """Set up auto-refresh timer."""
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_jobs)
        self.refresh_timer.start(self.refresh_interval_spin.value() * 1000)

    def _cleanup_query_thread(self):
        """Clean up previous query thread and worker to prevent memory leaks."""
        if self.query_worker is not None:
            try:
                self.query_worker.jobs_updated.disconnect()
                self.query_worker.error.disconnect()
            except (TypeError, RuntimeError):
                pass  # Already disconnected or deleted
            self.query_worker.deleteLater()
            self.query_worker = None

        if self.query_thread is not None:
            if self.query_thread.isRunning():
                self.query_thread.quit()
                self.query_thread.wait(500)
            try:
                self.query_thread.deleteLater()
            except RuntimeError:
                pass
            self.query_thread = None

    def refresh_jobs(self):
        """Fetch jobs using worker thread."""
        # Don't query if not connected
        if not self.ssh_manager.is_connected():
            return

        if self.query_thread is not None and self.query_thread.isRunning():
            logger.debug("Job query already in progress")
            return

        # Show loading state immediately so the user sees feedback
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("Refreshing…")

        # Clean up previous thread/worker before creating new ones
        self._cleanup_query_thread()

        self.query_thread = QThread()
        # Filter jobs by connected user
        username = None
        if hasattr(self.ssh_manager, '_profile') and self.ssh_manager._profile:
            username = self.ssh_manager._profile.username
        self.query_worker = JobQueryWorker(self.slurm_manager, user=username)
        self.query_worker.moveToThread(self.query_thread)

        self.query_worker.jobs_updated.connect(self.on_jobs_updated)
        self.query_worker.error.connect(self._on_query_error)
        self.query_thread.started.connect(self.query_worker.run)
        # Auto-cleanup when thread finishes
        self.query_worker.finished.connect(self.query_thread.quit)
        self.query_worker.finished.connect(self._restore_refresh_btn)

        self.query_thread.start()

    def on_jobs_updated(self, jobs):
        """
        Callback when job query worker completes.

        Args:
            jobs: List of JobInfo objects
        """
        self.job_table.update_jobs(jobs)
        logger.debug(f"Updated {len(jobs)} jobs in table")

    def _on_query_error(self, error: str):
        """
        Handle job query error.

        Args:
            error: Error message
        """
        logger.error(f"Job query error: {error}")
        # Optionally show error to user
        # QMessageBox.warning(self, "Error", f"Failed to query jobs: {error}")

    def _restore_refresh_btn(self):
        """Re-enable the Refresh button after a query finishes."""
        self.refresh_btn.setText("Refresh")
        self.refresh_btn.setEnabled(True)

    def on_submit_job(self):
        """Open job submit dialog."""
        dialog = JobSubmitDialog(
            self.slurm_manager,
            self.sftp_manager,
            self.database,
            self
        )
        dialog.job_submitted.connect(self._on_job_submitted)
        dialog.exec_()

    def _on_job_submitted(self, job_id: str):
        """
        Handle successful job submission.

        Args:
            job_id: Submitted job ID
        """
        logger.info(f"Job submitted: {job_id}")
        # Refresh job list after a short delay to let SLURM process it
        QTimer.singleShot(1000, self.refresh_jobs)

    def _launch_cancel(self, job_ids: list):
        """Run scancel for given job IDs in a background thread."""
        if self.cancel_thread and self.cancel_thread.isRunning():
            logger.warning("Cancel already in progress")
            return

        self._cleanup_cancel_thread()

        self.cancel_thread = QThread()
        self.cancel_worker = CancelJobWorker(self.ssh_manager, job_ids)
        self.cancel_worker.moveToThread(self.cancel_thread)

        self.cancel_thread.started.connect(self.cancel_worker.run)
        self.cancel_worker.results_ready.connect(self._on_cancel_results)
        self.cancel_worker.finished.connect(self.cancel_thread.quit)
        self.cancel_thread.finished.connect(
            lambda: self._cleanup_cancel_thread()
        )

        self.cancel_thread.start()
        logger.info(f"Cancel worker started for jobs: {job_ids}")

    def on_cancel_job(self):
        """Cancel selected job(s) with confirmation (supports multi-select).

        Runs scancel in a background thread so the UI stays responsive.
        """
        jobs = self.job_table.get_selected_jobs()
        if not jobs:
            QMessageBox.warning(
                self, "Error",
                "Please select one or more jobs to cancel."
            )
            return

        # Snapshot job IDs and info now (before any refresh can change the list)
        cancellable = [
            (j.job_id, j.name, j.state)
            for j in jobs if j.state.upper() in ("RUNNING", "PENDING")
        ]
        skipped = [
            (j.job_id, j.state)
            for j in jobs if j.state.upper() not in ("RUNNING", "PENDING")
        ]

        if not cancellable:
            states = ", ".join(f"{jid} ({st})" for jid, st in skipped)
            QMessageBox.warning(
                self, "Error",
                f"No selected jobs can be cancelled.\n"
                f"Non-cancellable: {states}"
            )
            return

        # Build confirmation message
        if len(cancellable) == 1:
            jid, jname, _ = cancellable[0]
            msg = f"Cancel job {jid} ({jname})?"
        else:
            job_list = "\n".join(
                f"  - {jid} ({jname})" for jid, jname, _ in cancellable
            )
            msg = f"Cancel {len(cancellable)} job(s)?\n\n{job_list}"

        if skipped:
            skip_list = ", ".join(f"{jid} ({st})" for jid, st in skipped)
            msg += f"\n\nSkipping non-cancellable: {skip_list}"

        # Pause auto-refresh while the dialog is shown to prevent table mutation
        was_running = self.refresh_timer and self.refresh_timer.isActive()
        if was_running:
            self.refresh_timer.stop()

        reply = QMessageBox.question(
            self, "Confirm Cancel", msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if was_running:
            self.refresh_timer.start()

        if reply != QMessageBox.Yes:
            return

        job_ids = [jid for jid, _, _ in cancellable]
        self._launch_cancel(job_ids)

    def _on_cancel_results(self, succeeded: list, failed: list):
        """Handle cancel worker results on the main thread."""
        if succeeded and not failed:
            QMessageBox.information(
                self, "Success",
                f"Cancelled {len(succeeded)} job(s): {', '.join(succeeded)}"
            )
        elif succeeded and failed:
            QMessageBox.warning(
                self, "Partial Success",
                f"Cancelled: {', '.join(succeeded)}\n"
                f"Failed: {', '.join(failed)}"
            )
        elif failed:
            QMessageBox.warning(
                self, "Error",
                f"Failed to cancel: {', '.join(failed)}"
            )

        # Refresh job list after cancel
        self.refresh_jobs()

    def _cleanup_cancel_thread(self):
        """Clean up previous cancel thread and worker."""
        if self.cancel_worker is not None:
            try:
                self.cancel_worker.results_ready.disconnect()
            except (TypeError, RuntimeError):
                pass
            try:
                self.cancel_worker.deleteLater()
            except RuntimeError:
                pass
            self.cancel_worker = None

        if self.cancel_thread is not None:
            if self.cancel_thread.isRunning():
                self.cancel_thread.quit()
                self.cancel_thread.wait(2000)
            try:
                self.cancel_thread.deleteLater()
            except RuntimeError:
                pass
            self.cancel_thread = None

    def on_view_log(self, job: Optional[JobInfo] = None):
        """Open log viewer for the selected job."""
        if job is None:
            job = self.job_table.get_selected_job()

        if not job:
            QMessageBox.warning(
                self, "Error",
                "Please select a job to view logs."
            )
            return

        # Use the output_file from squeue if available, otherwise default
        if getattr(job, 'output_file', '') and job.output_file:
            log_path = job.output_file
        elif getattr(job, 'work_dir', '') and job.work_dir:
            log_path = f"{job.work_dir}/slurm-{job.job_id}.out"
        else:
            log_path = f"slurm-{job.job_id}.out"

        log_dialog = LogViewerDialog(
            self.ssh_manager,
            job.job_id,
            log_path,
            self
        )
        log_dialog.exec_()

    def on_job_selected(self, job):
        """
        Update details panel with selected job info.

        Handles both slurm_manager.JobInfo and models.job.JobInfo.

        Args:
            job: Selected JobInfo object
        """
        # Update detail fields (use getattr for compatibility)
        self.detail_fields['job_id'].setText(str(getattr(job, 'job_id', '')))
        self.detail_fields['name'].setText(str(getattr(job, 'name', '')))
        self.detail_fields['user'].setText(str(getattr(job, 'user', '')))
        self.detail_fields['state'].setText(str(getattr(job, 'state', '')))
        self.detail_fields['queue'].setText(str(getattr(job, 'queue', getattr(job, 'partition', ''))))
        self.detail_fields['nodes'].setText(str(getattr(job, 'nodes', 0)))
        self.detail_fields['cpus'].setText(str(getattr(job, 'cpus', 0)))
        mem_gb = getattr(job, 'memory_gb', getattr(job, 'mem_per_node', 0))
        if isinstance(mem_gb, (int, float)):
            self.detail_fields['memory'].setText(f"{mem_gb:.2f} GB")
        else:
            self.detail_fields['memory'].setText(str(mem_gb))
        self.detail_fields['time_limit'].setText(str(getattr(job, 'time_limit', '')))
        self.detail_fields['elapsed'].setText(str(getattr(job, 'elapsed', getattr(job, 'time_used', ''))))
        start_time = getattr(job, 'start_time', None)
        self.detail_fields['start_time'].setText(
            start_time.strftime("%Y-%m-%d %H:%M:%S")
            if start_time else "-"
        )
        self.detail_fields['node_list'].setText(str(getattr(job, 'node_list', '')))
        self.detail_fields['exit_code'].setText(str(getattr(job, 'exit_code', -1)))

        # Try to load job output and script from metadata
        # This is a placeholder - actual implementation would query the system
        self.output_text.setPlainText("(Job output not yet implemented)")
        self.script_text.setPlainText("(Job script not yet implemented)")

    def _on_resubmit_selected(self):
        """Resubmit the currently selected job."""
        job = self.job_table.get_selected_job()
        if not job:
            QMessageBox.warning(self, "Error", "Please select a job to resubmit.")
            return
        self._on_resubmit_job(job)

    def _on_resubmit_job(self, job):
        """Resubmit a job by re-running its sbatch script.

        Locates the job's submission script via scontrol and runs sbatch
        from the job's working directory.
        """
        if not self.ssh_manager.is_connected():
            QMessageBox.warning(self, "Not Connected", "Please connect first.")
            return

        try:
            import shlex, re as _re
            # Get job script path from scontrol (portable: no grep -P)
            stdout, stderr, code = self.ssh_manager.execute_command(
                f"scontrol show job {shlex.quote(str(job.job_id))}",
                timeout=10
            )
            script_path = ''
            if code == 0 and stdout:
                m = _re.search(r'Command=(\S+)', stdout)
                if m:
                    script_path = m.group(1)

            if not script_path:
                # Fallback: try common patterns
                work_dir = getattr(job, 'work_dir', '') or job.metadata.get('work_dir', '')
                if work_dir:
                    script_path = f"{work_dir}/submit.sh"
                else:
                    QMessageBox.warning(
                        self, "Cannot Resubmit",
                        f"Could not find submission script for job {job.job_id}.\n"
                        f"scontrol output: {stderr.strip()}"
                    )
                    return

            # Confirm
            reply = QMessageBox.question(
                self, "Resubmit Job",
                f"Resubmit job {job.job_id} ({job.name})?\n\n"
                f"Script: {script_path}",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

            # Determine working directory
            work_dir = getattr(job, 'work_dir', '') or job.metadata.get('work_dir', '')
            if work_dir:
                cmd = f"cd {shlex.quote(work_dir)} && sbatch {shlex.quote(script_path)}"
            else:
                cmd = f"sbatch {shlex.quote(script_path)}"

            stdout, stderr, code = self.ssh_manager.execute_command(cmd, timeout=15)

            if code == 0 and stdout.strip():
                QMessageBox.information(
                    self, "Job Submitted",
                    f"Resubmitted successfully!\n{stdout.strip()}"
                )
                QTimer.singleShot(1000, self.refresh_jobs)
            else:
                QMessageBox.warning(
                    self, "Submission Failed",
                    f"sbatch failed (exit code {code}):\n{stderr.strip()}"
                )

        except Exception as e:
            logger.error(f"Resubmit failed: {e}")
            QMessageBox.critical(self, "Error", f"Resubmit failed: {e}")

    def _on_auto_refresh_toggled(self, checked: bool):
        """
        Handle auto-refresh toggle.

        Args:
            checked: Whether auto-refresh is enabled
        """
        if checked:
            self.refresh_timer.start()
        else:
            self.refresh_timer.stop()

    def _on_refresh_interval_changed(self, value: int):
        """
        Handle refresh interval change.

        Args:
            value: New interval in seconds
        """
        self.refresh_timer.setInterval(value * 1000)

    def _on_templates_clicked(self):
        """Open job template management dialog."""
        dialog = JobTemplateDialog(self.database, self)
        dialog.exec_()

    def closeEvent(self, event):
        """
        Handle widget close.

        Args:
            event: Close event
        """
        # Stop refresh timer
        if self.refresh_timer:
            self.refresh_timer.stop()

        # Stop worker threads (with bounded timeout to avoid hanging on exit)
        if self.query_thread and self.query_thread.isRunning():
            if self.query_worker:
                self.query_worker.cancel()
            self.query_thread.quit()
            if not self.query_thread.wait(3000):
                logger.warning("Query thread did not exit within timeout")

        # Stop cancel thread
        if self.cancel_thread and self.cancel_thread.isRunning():
            self.cancel_thread.quit()
            if not self.cancel_thread.wait(3000):
                logger.warning("Cancel thread did not exit within timeout")

        super().closeEvent(event)
