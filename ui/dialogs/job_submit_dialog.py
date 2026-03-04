"""
Multi-step GROMACS job submission wizard.

This module provides a JobSubmitDialog that guides users through creating
and submitting GROMACS jobs to SLURM with a multi-step wizard interface.
"""

import logging
from typing import Optional, List
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QStackedWidget, QWidget,
    QLabel, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QPushButton, QFormLayout, QPlainTextEdit, QCheckBox,
    QMessageBox, QProgressBar
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

from transfpro.core.slurm_manager import SLURMManager, PartitionInfo
from transfpro.core.sftp_manager import SFTPManager
from transfpro.core.database import Database
from transfpro.core.example_templates import ExampleTemplates
from transfpro.workers.job_submit_worker import JobSubmitWorker

logger = logging.getLogger(__name__)


class JobSubmitDialog(QDialog):
    """Multi-step wizard for submitting GROMACS jobs to SLURM."""

    job_submitted = pyqtSignal(str)  # job_id

    def __init__(self, slurm_manager: SLURMManager, sftp_manager: SFTPManager,
                 database: Database, parent=None):
        """
        Initialize the job submission dialog.

        Args:
            slurm_manager: SLURMManager instance
            sftp_manager: SFTPManager instance
            database: Database instance
            parent: Parent widget
        """
        super().__init__(parent)
        self.slurm_manager = slurm_manager
        self.sftp_manager = sftp_manager
        self.database = database
        self.partitions: List[PartitionInfo] = []
        self.modules: List[str] = []

        self.setWindowTitle("Submit GROMACS Job")
        self.setMinimumSize(700, 600)
        self._setup_ui()
        self._load_options()

    def _setup_ui(self):
        """Set up the UI layout."""
        layout = QVBoxLayout()

        # Page indicator
        page_layout = QHBoxLayout()
        self.page_label = QLabel("Step 1 of 5: Job Basics")
        self.page_label.setFont(QFont(QFont().family(), 12, QFont.Bold))
        page_layout.addWidget(self.page_label)
        page_layout.addStretch()
        layout.addLayout(page_layout)

        # Stacked widget for pages
        self.stacked = QStackedWidget()
        self._create_pages()
        layout.addWidget(self.stacked)

        # Button layout
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.back_button = QPushButton("Back")
        self.back_button.setMaximumWidth(100)
        self.back_button.clicked.connect(self._on_previous_page)
        button_layout.addWidget(self.back_button)

        self.next_button = QPushButton("Next")
        self.next_button.setMaximumWidth(100)
        self.next_button.clicked.connect(self._on_next_page)
        button_layout.addWidget(self.next_button)

        self.submit_button = QPushButton("Submit")
        self.submit_button.setMaximumWidth(100)
        self.submit_button.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; }"
        )
        self.submit_button.clicked.connect(self._on_submit)
        button_layout.addWidget(self.submit_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def _create_pages(self):
        """Create all wizard pages."""
        # Page 1: Job Basics
        page1 = self._create_page_basics()
        self.stacked.addWidget(page1)

        # Page 2: GROMACS Setup
        page2 = self._create_page_gromacs()
        self.stacked.addWidget(page2)

        # Page 3: Resources
        page3 = self._create_page_resources()
        self.stacked.addWidget(page3)

        # Page 4: Environment
        page4 = self._create_page_environment()
        self.stacked.addWidget(page4)

        # Page 5: Script Preview
        page5 = self._create_page_preview()
        self.stacked.addWidget(page5)

        self._update_button_states()

    def _create_page_basics(self) -> QWidget:
        """Create job basics page."""
        page = QWidget()
        layout = QFormLayout()

        self.job_name_input = QLineEdit()
        self.job_name_input.setPlaceholderText("e.g., my_simulation")
        layout.addRow("Job Name:", self.job_name_input)

        self.workflow_combo = QComboBox()
        self.workflow_combo.addItems(
            [t["name"] for t in ExampleTemplates.TEMPLATES.values()]
        )
        layout.addRow("Workflow Type:", self.workflow_combo)

        self.partition_combo = QComboBox()
        layout.addRow("Partition:", self.partition_combo)

        self.account_input = QLineEdit()
        self.account_input.setPlaceholderText("Optional")
        layout.addRow("Account:", self.account_input)

        self.time_limit_spin = QSpinBox()
        self.time_limit_spin.setMinimum(1)
        self.time_limit_spin.setMaximum(1440)  # 24 hours
        self.time_limit_spin.setValue(60)
        self.time_limit_spin.setSuffix(" minutes")
        layout.addRow("Time Limit:", self.time_limit_spin)

        page.setLayout(layout)
        return page

    def _create_page_gromacs(self) -> QWidget:
        """Create GROMACS setup page."""
        page = QWidget()
        layout = QFormLayout()

        self.tpr_input = QLineEdit()
        self.tpr_input.setPlaceholderText("Remote path to TPR file")
        layout.addRow("TPR/Input File:", self.tpr_input)

        self.output_prefix_input = QLineEdit()
        self.output_prefix_input.setPlaceholderText("e.g., em, nvt")
        layout.addRow("Output Prefix:", self.output_prefix_input)

        self.work_dir_input = QLineEdit()
        self.work_dir_input.setPlaceholderText("Remote working directory")
        layout.addRow("Working Directory:", self.work_dir_input)

        self.gromacs_flags_input = QLineEdit()
        self.gromacs_flags_input.setPlaceholderText("-ntomp 8 -gpu_id 0")
        layout.addRow("GROMACS Flags:", self.gromacs_flags_input)

        page.setLayout(layout)
        return page

    def _create_page_resources(self) -> QWidget:
        """Create resources page."""
        page = QWidget()
        layout = QFormLayout()

        self.nodes_spin = QSpinBox()
        self.nodes_spin.setMinimum(1)
        self.nodes_spin.setMaximum(100)
        self.nodes_spin.setValue(1)
        layout.addRow("Nodes:", self.nodes_spin)

        self.cpus_per_node_spin = QSpinBox()
        self.cpus_per_node_spin.setMinimum(1)
        self.cpus_per_node_spin.setMaximum(128)
        self.cpus_per_node_spin.setValue(8)
        layout.addRow("CPUs per Node:", self.cpus_per_node_spin)

        self.gpus_spin = QSpinBox()
        self.gpus_spin.setMinimum(0)
        self.gpus_spin.setMaximum(8)
        self.gpus_spin.setValue(0)
        layout.addRow("GPUs:", self.gpus_spin)

        self.memory_combo = QComboBox()
        self.memory_combo.addItems(
            ["2G", "4G", "8G", "16G", "32G", "64G", "128G"]
        )
        self.memory_combo.setCurrentText("8G")
        layout.addRow("Memory per Node:", self.memory_combo)

        self.email_check = QCheckBox("Enable email notifications")
        layout.addRow("Notifications:", self.email_check)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("your@email.com")
        self.email_input.setEnabled(False)
        self.email_check.toggled.connect(self.email_input.setEnabled)
        layout.addRow("Email:", self.email_input)

        page.setLayout(layout)
        return page

    def _create_page_environment(self) -> QWidget:
        """Create environment page."""
        page = QWidget()
        layout = QFormLayout()

        self.gromacs_module_combo = QComboBox()
        layout.addRow("GROMACS Module:", self.gromacs_module_combo)

        self.additional_modules_input = QLineEdit()
        self.additional_modules_input.setPlaceholderText("e.g., cuda/11.0, gcc/9.3")
        layout.addRow("Additional Modules:", self.additional_modules_input)

        self.custom_env_text = QPlainTextEdit()
        self.custom_env_text.setPlaceholderText(
            "export OMP_NUM_THREADS=4\nexport CUDA_VISIBLE_DEVICES=0"
        )
        self.custom_env_text.setMaximumHeight(150)
        layout.addRow("Custom Environment:", self.custom_env_text)

        page.setLayout(layout)
        return page

    def _create_page_preview(self) -> QWidget:
        """Create script preview page."""
        page = QWidget()
        layout = QVBoxLayout()

        label = QLabel("Review the generated sbatch script:")
        layout.addWidget(label)

        self.script_text = QPlainTextEdit()
        self.script_text.setFont(
            QFont("Courier New", 9)
        )
        layout.addWidget(self.script_text)

        # Buttons for script actions
        button_layout = QHBoxLayout()
        gen_button = QPushButton("Regenerate from Template")
        gen_button.clicked.connect(self._regenerate_script)
        button_layout.addWidget(gen_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        page.setLayout(layout)
        return page

    def _load_options(self):
        """Load partition and module options."""
        try:
            # Load partitions
            self.partitions = self.slurm_manager.get_partitions()
            partition_names = [p.name for p in self.partitions]
            if partition_names:
                self.partition_combo = self.stacked.widget(0).findChild(
                    QComboBox, "partition_combo"
                )
                # Find partition combo in form
                for i in range(self.stacked.widget(0).layout().rowCount()):
                    row_widget = self.stacked.widget(0).layout().itemAt(i, 1).widget()
                    if isinstance(row_widget, QComboBox):
                        row_widget.addItems(partition_names)
                        break

            # Load GROMACS modules
            self.modules = self.slurm_manager.get_available_modules("gromacs")
            if self.modules:
                self.gromacs_module_combo.addItems(self.modules)

        except Exception as e:
            logger.error(f"Failed to load options: {e}")
            QMessageBox.warning(
                self, "Warning",
                f"Failed to load some options. Please check your connection.\n{e}"
            )

    def _on_next_page(self):
        """Go to next page."""
        if self.stacked.currentIndex() < self.stacked.count() - 1:
            self.stacked.setCurrentIndex(self.stacked.currentIndex() + 1)
            self._update_page_label()
            self._update_button_states()

            # Generate script preview on last page
            if self.stacked.currentIndex() == self.stacked.count() - 1:
                self._generate_script()

    def _on_previous_page(self):
        """Go to previous page."""
        if self.stacked.currentIndex() > 0:
            self.stacked.setCurrentIndex(self.stacked.currentIndex() - 1)
            self._update_page_label()
            self._update_button_states()

    def _update_page_label(self):
        """Update page indicator label."""
        current_page = self.stacked.currentIndex() + 1
        total_pages = self.stacked.count()
        steps = [
            "Job Basics",
            "GROMACS Setup",
            "Resources",
            "Environment",
            "Script Preview"
        ]
        self.page_label.setText(f"Step {current_page} of {total_pages}: {steps[current_page - 1]}")

    def _update_button_states(self):
        """Update button enabled states."""
        is_first = self.stacked.currentIndex() == 0
        is_last = self.stacked.currentIndex() == self.stacked.count() - 1

        self.back_button.setEnabled(not is_first)
        self.next_button.setEnabled(not is_last)
        self.next_button.setVisible(not is_last)
        self.submit_button.setVisible(is_last)

    def _generate_script(self) -> str:
        """
        Generate sbatch script from wizard inputs.

        Returns:
            Generated sbatch script content
        """
        script = "#!/bin/bash\n"
        script += f"#SBATCH --job-name={self.job_name_input.text()}\n"
        script += f"#SBATCH --partition={self.partition_combo.currentText()}\n"
        script += f"#SBATCH --nodes={self.nodes_spin.value()}\n"
        script += f"#SBATCH --cpus-per-task={self.cpus_per_node_spin.value()}\n"

        if self.gpus_spin.value() > 0:
            script += f"#SBATCH --gpus={self.gpus_spin.value()}\n"

        script += f"#SBATCH --mem={self.memory_combo.currentText()}\n"
        script += f"#SBATCH --time={self.time_limit_spin.value()}:00\n"

        if self.email_check.isChecked() and self.email_input.text():
            script += f"#SBATCH --mail-user={self.email_input.text()}\n"
            script += "#SBATCH --mail-type=ALL\n"

        script += "\n# Environment setup\n"

        if self.gromacs_module_combo.currentText():
            script += f"module load {self.gromacs_module_combo.currentText()}\n"

        if self.additional_modules_input.text():
            modules = self.additional_modules_input.text().split(',')
            for mod in modules:
                script += f"module load {mod.strip()}\n"

        if self.custom_env_text.toPlainText():
            script += "\n" + self.custom_env_text.toPlainText() + "\n"

        script += "\n# Change to working directory\n"
        script += f"cd {self.work_dir_input.text()}\n"

        script += "\n# Run GROMACS\n"
        script += f"gmx mdrun -deffnm {self.output_prefix_input.text()}"

        if self.gromacs_flags_input.text():
            script += f" {self.gromacs_flags_input.text()}"

        script += "\n"

        self.script_text.setPlainText(script)
        return script

    def _regenerate_script(self):
        """Regenerate script from template."""
        self._generate_script()

    def _save_template(self):
        """Save current configuration as template."""
        # This would open a save template dialog
        pass

    def _on_submit(self):
        """Submit the job."""
        try:
            if not self._validate_inputs():
                QMessageBox.warning(
                    self, "Validation Error",
                    "Please fill in all required fields."
                )
                return

            script_content = self.script_text.toPlainText()

            # Use worker thread for submission
            self.submit_thread = QThread()
            self.submit_worker = JobSubmitWorker(
                self.slurm_manager,
                script_content,
                self.work_dir_input.text()
            )
            self.submit_worker.moveToThread(self.submit_thread)

            self.submit_worker.job_submitted.connect(self._on_job_submitted)
            self.submit_worker.error.connect(self._on_submit_error)
            self.submit_thread.started.connect(self.submit_worker.run)

            self.submit_button.setEnabled(False)
            self.submit_button.setText("Submitting...")

            self.submit_thread.start()

        except Exception as e:
            logger.error(f"Submission error: {e}", exc_info=True)
            QMessageBox.critical(
                self, "Submission Error",
                f"Failed to submit job: {str(e)}"
            )

    def _on_job_submitted(self, job_id: str):
        """
        Handle successful job submission.

        Args:
            job_id: Submitted job ID
        """
        self.submit_button.setEnabled(True)
        self.submit_button.setText("Submit")
        self.submit_thread.quit()
        self.submit_thread.wait()

        QMessageBox.information(
            self, "Success",
            f"Job submitted successfully!\nJob ID: {job_id}"
        )

        self.job_submitted.emit(job_id)
        self.accept()

    def _on_submit_error(self, error: str):
        """
        Handle job submission error.

        Args:
            error: Error message
        """
        self.submit_button.setEnabled(True)
        self.submit_button.setText("Submit")
        self.submit_thread.quit()
        self.submit_thread.wait()

        QMessageBox.critical(
            self, "Submission Error",
            f"Failed to submit job:\n{error}"
        )

    def _validate_inputs(self) -> bool:
        """
        Validate all required inputs.

        Returns:
            True if all inputs are valid
        """
        return (
            bool(self.job_name_input.text().strip()) and
            bool(self.tpr_input.text().strip()) and
            bool(self.output_prefix_input.text().strip()) and
            bool(self.work_dir_input.text().strip())
        )
