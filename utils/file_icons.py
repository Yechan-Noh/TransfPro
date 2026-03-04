"""
TransfPro File Icon Utilities

This module provides functions to map file extensions to Qt icon pixmaps,
with special handling for GROMACS-specific file types.
"""

from typing import Dict, Optional
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QApplication, QStyle
from PyQt5.QtCore import QSize

try:
    from ..core.gromacs_parser import (
        GROMACS_EXTENSIONS,
        GROMACS_INPUT_EXTENSIONS,
        GROMACS_OUTPUT_EXTENSIONS,
    )
except ImportError:
    GROMACS_EXTENSIONS = set()
    GROMACS_INPUT_EXTENSIONS = set()
    GROMACS_OUTPUT_EXTENSIONS = set()


# File extension to QStyle icon role mapping
EXTENSION_TO_ICON_ROLE: Dict[str, QStyle.StandardPixmap] = {
    # Document types
    ".txt": QStyle.StandardPixmap.SP_FileIcon,
    ".pdf": QStyle.StandardPixmap.SP_FileIcon,
    ".doc": QStyle.StandardPixmap.SP_FileIcon,
    ".docx": QStyle.StandardPixmap.SP_FileIcon,
    ".odt": QStyle.StandardPixmap.SP_FileIcon,
    # Source code
    ".py": QStyle.StandardPixmap.SP_FileIcon,
    ".sh": QStyle.StandardPixmap.SP_FileIcon,
    ".c": QStyle.StandardPixmap.SP_FileIcon,
    ".cpp": QStyle.StandardPixmap.SP_FileIcon,
    ".h": QStyle.StandardPixmap.SP_FileIcon,
    ".java": QStyle.StandardPixmap.SP_FileIcon,
    # Archives
    ".zip": QStyle.StandardPixmap.SP_FileIcon,
    ".tar": QStyle.StandardPixmap.SP_FileIcon,
    ".gz": QStyle.StandardPixmap.SP_FileIcon,
    ".tar.gz": QStyle.StandardPixmap.SP_FileIcon,
    ".7z": QStyle.StandardPixmap.SP_FileIcon,
    ".rar": QStyle.StandardPixmap.SP_FileIcon,
    # Images
    ".png": QStyle.StandardPixmap.SP_FileIcon,
    ".jpg": QStyle.StandardPixmap.SP_FileIcon,
    ".jpeg": QStyle.StandardPixmap.SP_FileIcon,
    ".gif": QStyle.StandardPixmap.SP_FileIcon,
    ".bmp": QStyle.StandardPixmap.SP_FileIcon,
    # Data files
    ".csv": QStyle.StandardPixmap.SP_FileIcon,
    ".json": QStyle.StandardPixmap.SP_FileIcon,
    ".xml": QStyle.StandardPixmap.SP_FileIcon,
    ".yaml": QStyle.StandardPixmap.SP_FileIcon,
    ".yml": QStyle.StandardPixmap.SP_FileIcon,
}

# GROMACS file extension descriptions
GROMACS_FILE_DESCRIPTIONS: Dict[str, str] = {
    ".tpr": "GROMACS Portable Binary Input File",
    ".mdp": "GROMACS Molecular Dynamics Parameters",
    ".gro": "GROMACS Structure Format",
    ".top": "GROMACS Topology File",
    ".xtc": "GROMACS Trajectory (Compressed)",
    ".edr": "GROMACS Energy File",
    ".log": "GROMACS Log File",
    ".cpt": "GROMACS Checkpoint File",
    ".trr": "GROMACS Trajectory (Uncompressed)",
    ".xvg": "GROMACS Data/Graph File",
}

# Color codes for different file types
FILE_TYPE_COLORS: Dict[str, str] = {
    "gromacs_input": "#2196F3",    # Blue
    "gromacs_output": "#4CAF50",   # Green
    "gromacs_data": "#FF9800",     # Orange
    "document": "#9C27B0",          # Purple
    "archive": "#F44336",           # Red
    "source_code": "#00BCD4",       # Cyan
    "image": "#E91E63",             # Pink
    "default": "#757575",           # Grey
}


def get_file_extension(filename: str) -> str:
    """
    Extract file extension from filename.

    Handles compound extensions like .tar.gz.

    Args:
        filename: Name of the file

    Returns:
        str: File extension in lowercase (including the dot)

    Examples:
        >>> get_file_extension("simulation.mdp")
        '.mdp'
        >>> get_file_extension("archive.tar.gz")
        '.tar.gz'
    """
    if not filename:
        return ""

    filename_lower = filename.lower()

    # Handle compound extensions
    if filename_lower.endswith(".tar.gz"):
        return ".tar.gz"
    if filename_lower.endswith(".tar.bz2"):
        return ".tar.bz2"

    # Standard extension
    if "." in filename:
        return "." + filename_lower.split(".")[-1]

    return ""


def is_gromacs_file(filename: str) -> bool:
    """
    Check if a file is a GROMACS-related file.

    Args:
        filename: Name of the file

    Returns:
        bool: True if file is a GROMACS file, False otherwise

    Examples:
        >>> is_gromacs_file("simulation.tpr")
        True
        >>> is_gromacs_file("readme.txt")
        False
    """
    extension = get_file_extension(filename)
    return extension in GROMACS_EXTENSIONS


def is_gromacs_input_file(filename: str) -> bool:
    """
    Check if a file is a GROMACS input file.

    Args:
        filename: Name of the file

    Returns:
        bool: True if file is a GROMACS input file, False otherwise

    Examples:
        >>> is_gromacs_input_file("simulation.tpr")
        True
        >>> is_gromacs_input_file("trajectory.xtc")
        False
    """
    extension = get_file_extension(filename)
    return extension in GROMACS_INPUT_EXTENSIONS


def is_gromacs_output_file(filename: str) -> bool:
    """
    Check if a file is a GROMACS output file.

    Args:
        filename: Name of the file

    Returns:
        bool: True if file is a GROMACS output file, False otherwise

    Examples:
        >>> is_gromacs_output_file("trajectory.xtc")
        True
        >>> is_gromacs_output_file("simulation.tpr")
        False
    """
    extension = get_file_extension(filename)
    return extension in GROMACS_OUTPUT_EXTENSIONS


def get_file_icon(filename: str, icon_size: int = 16) -> QIcon:
    """
    Get an appropriate icon for a file based on its type.

    Returns QStyle standard pixmaps or colored placeholders for various file types,
    with special handling for GROMACS files.

    Args:
        filename: Name of the file
        icon_size: Size of the icon in pixels (default: 16)

    Returns:
        QIcon: Appropriate icon for the file type

    Examples:
        >>> icon = get_file_icon("simulation.mdp")
        >>> # Returns a GROMACS-specific icon
        >>> icon = get_file_icon("data.csv")
        >>> # Returns a generic document icon
    """
    if not filename:
        return _get_default_icon(icon_size)

    extension = get_file_extension(filename)

    # Get icon from QStyle standard pixmaps
    if extension in EXTENSION_TO_ICON_ROLE:
        return _get_styled_icon(
            EXTENSION_TO_ICON_ROLE[extension],
            icon_size,
        )

    # Handle GROMACS files with special coloring
    if extension in GROMACS_EXTENSIONS:
        if extension in GROMACS_INPUT_EXTENSIONS:
            color = FILE_TYPE_COLORS["gromacs_input"]
        elif extension in GROMACS_OUTPUT_EXTENSIONS:
            color = FILE_TYPE_COLORS["gromacs_output"]
        else:
            color = FILE_TYPE_COLORS["gromacs_data"]

        return _create_colored_icon(extension, color, icon_size)

    # Default icon
    return _get_default_icon(icon_size)


def get_file_icon_by_type(
    file_type: str,
    icon_size: int = 16,
) -> QIcon:
    """
    Get an icon for a specific file type category.

    Args:
        file_type: File type category (gromacs_input, document, archive, etc.)
        icon_size: Size of the icon in pixels

    Returns:
        QIcon: Icon for the file type

    Examples:
        >>> icon = get_file_icon_by_type("gromacs_input", 24)
        >>> icon = get_file_icon_by_type("document", 16)
    """
    type_to_icon: Dict[str, QStyle.StandardPixmap] = {
        "document": QStyle.StandardPixmap.SP_FileIcon,
        "directory": QStyle.StandardPixmap.SP_DirIcon,
        "archive": QStyle.StandardPixmap.SP_FileIcon,
        "image": QStyle.StandardPixmap.SP_FileIcon,
        "source_code": QStyle.StandardPixmap.SP_FileIcon,
    }

    icon_role = type_to_icon.get(file_type, QStyle.StandardPixmap.SP_FileIcon)
    return _get_styled_icon(icon_role, icon_size)


def get_directory_icon(icon_size: int = 16) -> QIcon:
    """
    Get an icon for a directory.

    Args:
        icon_size: Size of the icon in pixels

    Returns:
        QIcon: Directory icon
    """
    return _get_styled_icon(QStyle.StandardPixmap.SP_DirIcon, icon_size)


def get_file_type_description(filename: str) -> str:
    """
    Get a description of the file type.

    Args:
        filename: Name of the file

    Returns:
        str: Description of the file type

    Examples:
        >>> get_file_type_description("simulation.mdp")
        'GROMACS Molecular Dynamics Parameters'
        >>> get_file_type_description("data.csv")
        'Comma-Separated Values'
    """
    extension = get_file_extension(filename)

    # GROMACS files
    if extension in GROMACS_FILE_DESCRIPTIONS:
        return GROMACS_FILE_DESCRIPTIONS[extension]

    # Common file types
    type_descriptions: Dict[str, str] = {
        ".txt": "Text File",
        ".pdf": "PDF Document",
        ".csv": "Comma-Separated Values",
        ".json": "JSON Data File",
        ".xml": "XML Document",
        ".yaml": "YAML Configuration",
        ".yml": "YAML Configuration",
        ".py": "Python Source Code",
        ".sh": "Shell Script",
        ".c": "C Source Code",
        ".cpp": "C++ Source Code",
        ".h": "C Header File",
        ".java": "Java Source Code",
        ".zip": "ZIP Archive",
        ".tar": "TAR Archive",
        ".gz": "GZIP Compressed",
        ".tar.gz": "TAR GZIP Archive",
        ".7z": "7-Zip Archive",
        ".rar": "RAR Archive",
        ".png": "PNG Image",
        ".jpg": "JPEG Image",
        ".jpeg": "JPEG Image",
        ".gif": "GIF Image",
        ".bmp": "Bitmap Image",
    }

    return type_descriptions.get(extension, "Unknown File Type")


def get_file_type_color(filename: str) -> str:
    """
    Get the color code for a file type.

    Args:
        filename: Name of the file

    Returns:
        str: Hex color code for the file type

    Examples:
        >>> get_file_type_color("trajectory.xtc")
        '#4CAF50'
        >>> get_file_type_color("unknown.xyz")
        '#757575'
    """
    extension = get_file_extension(filename)

    if extension in GROMACS_INPUT_EXTENSIONS:
        return FILE_TYPE_COLORS["gromacs_input"]

    if extension in GROMACS_OUTPUT_EXTENSIONS:
        return FILE_TYPE_COLORS["gromacs_output"]

    return FILE_TYPE_COLORS["default"]


# Helper functions


def _get_styled_icon(
    pixmap: QStyle.StandardPixmap,
    size: int = 16,
) -> QIcon:
    """
    Get an icon from QStyle standard pixmaps.

    Args:
        pixmap: QStyle.StandardPixmap enum value
        size: Icon size in pixels

    Returns:
        QIcon: The requested icon
    """
    app = QApplication.instance()
    if app and hasattr(app, "style"):
        icon = app.style().standardIcon(pixmap)
        if not icon.isNull():
            return icon

    # Fallback: create colored placeholder
    return _create_colored_icon("F", "#757575", size)


def _get_default_icon(size: int = 16) -> QIcon:
    """
    Get the default file icon.

    Args:
        size: Icon size in pixels

    Returns:
        QIcon: Default file icon
    """
    return _get_styled_icon(QStyle.StandardPixmap.SP_FileIcon, size)


def _create_colored_icon(
    letter: str,
    color: str,
    size: int = 16,
) -> QIcon:
    """
    Create a colored placeholder icon with a letter.

    Args:
        letter: Single letter to display on the icon
        color: Hex color code for the background
        size: Icon size in pixels

    Returns:
        QIcon: Colored icon with letter
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(0)  # Transparent background

    # Create a colored square
    colored_pixmap = QPixmap(size, size)
    colored_pixmap.fill(color)

    # Return icon
    icon = QIcon(colored_pixmap)
    return icon
