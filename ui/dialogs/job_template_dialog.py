"""
Dialog for managing sbatch templates.

This module provides a JobTemplateDialog for creating, editing, and managing
SLURM sbatch script templates that can be reused for job submissions.
"""

import logging
from typing import Optional, Dict
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QFormLayout, QLineEdit, QPlainTextEdit, QPushButton, QMessageBox,
    QSplitter
)
from PyQt5.QtCore import Qt

from transfpro.core.database import Database

logger = logging.getLogger(__name__)


class JobTemplateDialog(QDialog):
    """Save/load/edit sbatch templates."""

    def __init__(self, database: Database, parent=None):
        """
        Initialize the template management dialog.

        Args:
            database: Database instance for template persistence
            parent: Parent widget
        """
        super().__init__(parent)
        self.database = database
        self.templates: Dict[str, Dict] = {}
        self.current_template: Optional[str] = None

        self.setWindowTitle("Manage Job Templates")
        self.setMinimumSize(800, 600)
        self._setup_ui()
        self._load_templates()

    def _setup_ui(self):
        """Set up the UI layout."""
        layout = QHBoxLayout()

        # Left: Template list
        left_layout = QVBoxLayout()

        left_label_layout = QHBoxLayout()
        left_layout.addLayout(left_label_layout)

        self.template_list = QListWidget()
        self.template_list.itemSelectionChanged.connect(self._on_template_selected)
        left_layout.addWidget(self.template_list)

        # Buttons for list
        list_button_layout = QHBoxLayout()
        new_btn = QPushButton("New")
        new_btn.clicked.connect(self._on_new_template)
        list_button_layout.addWidget(new_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self._on_delete_template)
        list_button_layout.addWidget(delete_btn)

        list_button_layout.addStretch()
        left_layout.addLayout(list_button_layout)

        # Right: Template editor
        right_layout = QVBoxLayout()

        editor_form = QFormLayout()

        self.name_input = QLineEdit()
        self.name_input.setReadOnly(True)
        editor_form.addRow("Template Name:", self.name_input)

        self.description_input = QLineEdit()
        editor_form.addRow("Description:", self.description_input)

        self.script_text = QPlainTextEdit()
        editor_form.addRow("Script Content:", self.script_text)

        right_layout.addLayout(editor_form)

        # Buttons for editor
        editor_button_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save_template)
        editor_button_layout.addWidget(save_btn)

        builtin_btn = QPushButton("Load Built-in Templates")
        builtin_btn.clicked.connect(self._on_load_builtins)
        editor_button_layout.addWidget(builtin_btn)

        editor_button_layout.addStretch()
        right_layout.addLayout(editor_button_layout)

        # Splitter
        splitter = QSplitter(Qt.Horizontal)

        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        right_widget = QWidget()
        right_widget.setLayout(right_layout)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter)

        # Close button
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_layout.addWidget(close_btn)

        main_layout = QVBoxLayout()
        main_layout.addLayout(layout)
        main_layout.addLayout(close_layout)

        self.setLayout(main_layout)

    def _load_templates(self):
        """Load templates from database."""
        try:
            # Load user templates from database
            cursor = self.database.connection.cursor()
            cursor.execute("""
                SELECT name, description, script_content FROM job_templates
                ORDER BY created_at DESC
            """)

            self.templates = {}
            for row in cursor.fetchall():
                name = row[0]
                self.templates[name] = {
                    'description': row[1],
                    'script_content': row[2]
                }

            self._refresh_template_list()

        except Exception as e:
            logger.error(f"Failed to load templates: {e}")

    def _refresh_template_list(self):
        """Refresh the template list widget."""
        self.template_list.clear()

        for name in sorted(self.templates.keys()):
            item = QListWidgetItem(name)
            self.template_list.addItem(item)

    def _on_template_selected(self):
        """Handle template selection."""
        items = self.template_list.selectedItems()
        if not items:
            return

        template_name = items[0].text()
        self.current_template = template_name
        template = self.templates.get(template_name, {})

        self.name_input.setText(template_name)
        self.description_input.setText(template.get('description', ''))
        self.script_text.setPlainText(template.get('script_content', ''))

    def _on_new_template(self):
        """Create a new template."""
        # Clear editor
        self.template_list.clearSelection()
        self.current_template = None
        self.name_input.setText("")
        self.description_input.setText("")
        self.script_text.setPlainText("#!/bin/bash\n#SBATCH --job-name=\n#SBATCH --partition=\n#SBATCH --nodes=1\n#SBATCH --cpus-per-task=8\n#SBATCH --time=01:00:00\n\n")

    def _on_save_template(self):
        """Save current template."""
        name = self.name_input.text().strip()
        if not name:
            name = self.current_template

        if not name:
            QMessageBox.warning(
                self, "Error",
                "Please enter a template name."
            )
            return

        description = self.description_input.text().strip()
        script_content = self.script_text.toPlainText()

        if not script_content.strip():
            QMessageBox.warning(
                self, "Error",
                "Please enter script content."
            )
            return

        try:
            cursor = self.database.connection.cursor()

            # Check if template exists
            cursor.execute(
                "SELECT COUNT(*) FROM job_templates WHERE name = ?",
                (name,)
            )

            exists = cursor.fetchone()[0] > 0

            if exists:
                # Update existing
                cursor.execute("""
                    UPDATE job_templates
                    SET description = ?, script_content = ?
                    WHERE name = ?
                """, (description, script_content, name))
            else:
                # Insert new
                cursor.execute("""
                    INSERT INTO job_templates
                    (name, description, script_content)
                    VALUES (?, ?, ?)
                """, (name, description, script_content))

            self.database.connection.commit()
            self.templates[name] = {
                'description': description,
                'script_content': script_content
            }
            self._refresh_template_list()
            self.current_template = name

            QMessageBox.information(
                self, "Success",
                f"Template '{name}' saved successfully."
            )

        except Exception as e:
            logger.error(f"Failed to save template: {e}")
            QMessageBox.critical(
                self, "Error",
                f"Failed to save template: {str(e)}"
            )

    def _on_delete_template(self):
        """Delete selected template."""
        if not self.current_template:
            QMessageBox.warning(
                self, "Error",
                "Please select a template to delete."
            )
            return

        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete template '{self.current_template}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        try:
            cursor = self.database.connection.cursor()
            cursor.execute(
                "DELETE FROM job_templates WHERE name = ?",
                (self.current_template,)
            )
            self.database.connection.commit()

            del self.templates[self.current_template]
            self._refresh_template_list()
            self.current_template = None

            # Clear editor
            self.name_input.setText("")
            self.description_input.setText("")
            self.script_text.setPlainText("")

            QMessageBox.information(
                self, "Success",
                "Template deleted successfully."
            )

        except Exception as e:
            logger.error(f"Failed to delete template: {e}")
            QMessageBox.critical(
                self, "Error",
                f"Failed to delete template: {str(e)}"
            )

    def _on_load_builtins(self):
        """Load built-in templates into database."""
        from transfpro.core.example_templates import ExampleTemplates

        try:
            cursor = self.database.connection.cursor()

            for template_id, template_data in ExampleTemplates.TEMPLATES.items():
                name = f"[Built-in] {template_data['name']}"
                description = template_data['description']
                script_content = template_data['script_template']

                # Check if already exists
                cursor.execute(
                    "SELECT COUNT(*) FROM job_templates WHERE name = ?",
                    (name,)
                )

                if cursor.fetchone()[0] == 0:
                    cursor.execute("""
                        INSERT INTO job_templates
                        (name, description, script_content)
                        VALUES (?, ?, ?)
                    """, (name, description, script_content))

            self.database.connection.commit()
            self._load_templates()

            QMessageBox.information(
                self, "Success",
                "Built-in templates loaded successfully."
            )

        except Exception as e:
            logger.error(f"Failed to load built-in templates: {e}")
            QMessageBox.critical(
                self, "Error",
                f"Failed to load built-in templates: {str(e)}"
            )
