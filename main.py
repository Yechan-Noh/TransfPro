"""
TransfPro Application Entry Point.

This module serves as the main entry point for the TransfPro application.
It initializes logging, creates the Qt application instance, and launches
the main window.

Usage:
    python -m transfpro
    or
    python transfpro/main.py
"""

import sys
import logging
import traceback
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QFont

from transfpro.ui.main_window import MainWindow
from transfpro.utils.logger import setup_logger, get_logger
from transfpro.config.constants import APP_NAME, APP_VERSION


# ---------------------------------------------------------------------------
# Crash reporting — write unhandled exceptions to ~/.transfpro/crash_reports/
# ---------------------------------------------------------------------------
_CRASH_DIR = Path.home() / ".transfpro" / "crash_reports"


def _crash_handler(exc_type, exc_value, exc_tb):
    """Global exception handler that writes crash reports to disk."""
    try:
        _CRASH_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = _CRASH_DIR / f"crash_{timestamp}.txt"
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
        with open(report_path, "w") as f:
            f.write(f"TransfPro v{APP_VERSION} Crash Report\n")
            f.write(f"Time: {datetime.now().isoformat()}\n")
            f.write(f"Python: {sys.version}\n")
            f.write("=" * 60 + "\n\n")
            f.writelines(tb_lines)
        logging.critical("".join(tb_lines))
    except Exception:
        pass  # Last resort — don't let the handler itself crash
    # Call the default handler so the process still terminates
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def setup_application():
    """
    Setup application metadata and return QApplication instance.

    Returns:
        QApplication: Configured Qt application instance
    """
    # High-DPI support (must be set before QApplication is created)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    # Set application metadata
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_NAME)

    # Set application icon
    try:
        icon_paths = [
            Path(__file__).parent / "resources" / "transfpro_icon.png",
            Path(__file__).parent / "ui" / "resources" / "icons" / "app_icon.png",
            Path(__file__).parent / "ui" / "resources" / "app_icon.png",
        ]
        for icon_path in icon_paths:
            if icon_path.exists():
                app.setWindowIcon(QIcon(str(icon_path)))
                break
    except Exception as e:
        logging.debug(f"Could not load application icon: {e}")

    # Apply saved font size
    try:
        from transfpro.config.settings import Settings
        settings = Settings()
        font_size = settings.get_value("appearance/font_size", 13)
        font = app.font()
        font.setPointSize(int(font_size))
        app.setFont(font)
    except Exception as e:
        logging.debug(f"Could not apply saved font size: {e}")

    return app


def main():
    """
    Main application entry point.

    Initializes logging, creates the Qt application, and displays the main window.
    Handles graceful shutdown on exit.
    """
    # Install global crash handler
    sys.excepthook = _crash_handler

    # Setup logging
    logger = setup_logger()
    logger.info("=" * 70)
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")
    logger.info("=" * 70)

    try:
        # Create Qt application
        app = setup_application()

        logger.info("Qt application initialized")
        logger.info(f"Qt version: {app.applicationVersion()}")

        # Create and show main window
        window = MainWindow()
        window.show()

        logger.info("Main window displayed")

        # Run event loop
        exit_code = app.exec_()

        logger.info(f"Application exiting with code {exit_code}")
        logger.info("=" * 70)

        return exit_code

    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
