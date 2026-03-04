"""
TransfPro Application Settings

This module provides a QSettings wrapper class for persistent application
settings like window geometry, themes, refresh intervals, and connection preferences.
"""

from typing import Any, Optional
from PyQt5.QtCore import QSettings, QSize, QPoint, QRect
from PyQt5.QtGui import QColor

from .constants import (
    DEFAULT_REFRESH_INTERVAL,
    MAX_CONCURRENT_TRANSFERS,
)


class Settings:
    """
    Wrapper around QSettings for application configuration.

    Provides type-safe access to application settings with sensible defaults.
    All settings are persisted to the system's native settings storage.

    Attributes:
        _settings: QSettings instance
    """

    def __init__(self) -> None:
        """Initialize the Settings wrapper with QSettings."""
        self._settings = QSettings("TransfPro", "TransfPro")

    # Connection Settings
    def get_last_connection_id(self) -> Optional[str]:
        """
        Get the ID of the last used connection.

        Returns:
            Optional[str]: Connection ID or None if not set
        """
        return self._settings.value("connection/last_connection_id", None, str)

    def set_last_connection_id(self, connection_id: str) -> None:
        """
        Set the ID of the last used connection.

        Args:
            connection_id: The connection ID to store
        """
        self._settings.setValue("connection/last_connection_id", connection_id)

    def get_remember_passwords(self) -> bool:
        """
        Get whether passwords should be remembered.

        Returns:
            bool: True if passwords should be remembered, False otherwise
        """
        return self._settings.value("connection/remember_passwords", False, bool)

    def set_remember_passwords(self, remember: bool) -> None:
        """
        Set whether passwords should be remembered.

        Args:
            remember: True to remember passwords, False otherwise
        """
        self._settings.setValue("connection/remember_passwords", remember)

    # Refresh and Polling Settings
    def get_auto_refresh_interval(self) -> int:
        """
        Get the automatic refresh interval in seconds.

        Returns:
            int: Refresh interval in seconds
        """
        return self._settings.value(
            "refresh/auto_refresh_interval",
            DEFAULT_REFRESH_INTERVAL,
            int,
        )

    def set_auto_refresh_interval(self, interval: int) -> None:
        """
        Set the automatic refresh interval in seconds.

        Args:
            interval: Refresh interval in seconds (must be positive)
        """
        if interval > 0:
            self._settings.setValue("refresh/auto_refresh_interval", interval)

    # Theme Settings
    def get_theme(self) -> str:
        """
        Get the current theme.

        Returns:
            str: Theme name ('dark' or 'light')
        """
        return self._settings.value("appearance/theme", "dark", str)

    def set_theme(self, theme: str) -> None:
        """
        Set the current theme.

        Args:
            theme: Theme name ('dark' or 'light')
        """
        if theme in ("dark", "light"):
            self._settings.setValue("appearance/theme", theme)

    def get_use_system_theme(self) -> bool:
        """
        Get whether to use system theme.

        Returns:
            bool: True to use system theme, False to use custom theme
        """
        return self._settings.value("appearance/use_system_theme", False, bool)

    def set_use_system_theme(self, use_system: bool) -> None:
        """
        Set whether to use system theme.

        Args:
            use_system: True to use system theme, False for custom theme
        """
        self._settings.setValue("appearance/use_system_theme", use_system)

    # File Transfer Settings
    def get_max_concurrent_transfers(self) -> int:
        """
        Get the maximum number of concurrent file transfers.

        Returns:
            int: Maximum concurrent transfers
        """
        return self._settings.value(
            "transfers/max_concurrent_transfers",
            MAX_CONCURRENT_TRANSFERS,
            int,
        )

    def set_max_concurrent_transfers(self, max_transfers: int) -> None:
        """
        Set the maximum number of concurrent file transfers.

        Args:
            max_transfers: Maximum concurrent transfers (must be positive)
        """
        if max_transfers > 0:
            self._settings.setValue("transfers/max_concurrent_transfers", max_transfers)

    def get_show_hidden_files(self) -> bool:
        """
        Get whether to show hidden files in file browsers.

        Returns:
            bool: True to show hidden files, False otherwise
        """
        return self._settings.value("files/show_hidden_files", False, bool)

    def set_show_hidden_files(self, show: bool) -> None:
        """
        Set whether to show hidden files in file browsers.

        Args:
            show: True to show hidden files, False otherwise
        """
        self._settings.setValue("files/show_hidden_files", show)

    def get_last_download_directory(self) -> str:
        """
        Get the last used download directory.

        Returns:
            str: Path to the last download directory
        """
        return self._settings.value("files/last_download_directory", "", str)

    def set_last_download_directory(self, directory: str) -> None:
        """
        Set the last used download directory.

        Args:
            directory: Path to the download directory
        """
        self._settings.setValue("files/last_download_directory", directory)

    # Window Geometry and State
    def get_window_geometry(self) -> Optional[QRect]:
        """
        Get the saved window geometry.

        Returns:
            Optional[QRect]: Saved window geometry or None if not set
        """
        value = self._settings.value("window/geometry", None)
        if value is not None and isinstance(value, QRect):
            return value
        return None

    def set_window_geometry(self, geometry: QRect) -> None:
        """
        Save the window geometry.

        Args:
            geometry: QRect representing the window geometry
        """
        self._settings.setValue("window/geometry", geometry)

    def get_window_state(self) -> Optional[bytes]:
        """
        Get the saved window state (minimized/maximized).

        Returns:
            Optional[bytes]: Saved window state or None if not set
        """
        return self._settings.value("window/state", None, bytes)

    def set_window_state(self, state: bytes) -> None:
        """
        Save the window state (minimized/maximized).

        Args:
            state: Bytes representing the window state
        """
        self._settings.setValue("window/state", state)

    def get_window_size(self) -> QSize:
        """
        Get the saved window size.

        Returns:
            QSize: Saved window size with sensible defaults
        """
        size = self._settings.value("window/size", None)
        if isinstance(size, QSize):
            return size
        return QSize(1200, 800)  # Default window size

    def set_window_size(self, size: QSize) -> None:
        """
        Save the window size.

        Args:
            size: QSize representing the window size
        """
        self._settings.setValue("window/size", size)

    # Splitter Sizes
    def get_splitter_sizes(self, splitter_name: str) -> Optional[list]:
        """
        Get saved splitter sizes by name.

        Args:
            splitter_name: Unique identifier for the splitter

        Returns:
            Optional[list]: List of splitter sizes or None if not set
        """
        return self._settings.value(f"splitters/{splitter_name}", None, list)

    def set_splitter_sizes(self, splitter_name: str, sizes: list) -> None:
        """
        Save splitter sizes by name.

        Args:
            splitter_name: Unique identifier for the splitter
            sizes: List of splitter sizes
        """
        self._settings.setValue(f"splitters/{splitter_name}", sizes)

    # Tab Index
    def get_active_tab_index(self, widget_name: str) -> int:
        """
        Get the previously active tab index for a widget.

        Args:
            widget_name: Unique identifier for the tab widget

        Returns:
            int: Active tab index (0-based)
        """
        return self._settings.value(f"tabs/{widget_name}", 0, int)

    def set_active_tab_index(self, widget_name: str, index: int) -> None:
        """
        Save the active tab index for a widget.

        Args:
            widget_name: Unique identifier for the tab widget
            index: Active tab index
        """
        if index >= 0:
            self._settings.setValue(f"tabs/{widget_name}", index)

    # Generic Get/Set Methods
    def get_value(self, key: str, default: Any = None) -> Any:
        """
        Get a generic setting value.

        Args:
            key: Setting key
            default: Default value if key not found

        Returns:
            Any: Setting value or default
        """
        return self._settings.value(key, default)

    def set_value(self, key: str, value: Any) -> None:
        """
        Set a generic setting value.

        Args:
            key: Setting key
            value: Value to set
        """
        self._settings.setValue(key, value)

    def remove(self, key: str) -> None:
        """
        Remove a setting.

        Args:
            key: Setting key to remove
        """
        self._settings.remove(key)

    def clear(self) -> None:
        """Clear all settings (use with caution)."""
        self._settings.clear()

    def sync(self) -> None:
        """Synchronize settings to disk immediately."""
        self._settings.sync()
