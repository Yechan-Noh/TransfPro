"""
File item models for TransfPro.

This module defines data models for representing remote file metadata
and properties for file transfer operations and browsing.
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any


class FileType(Enum):
    """Enumeration of file types."""

    FILE = "file"
    DIRECTORY = "directory"
    SYMLINK = "symlink"


@dataclass
class FileMetadata:
    """
    Represents metadata about a file or directory on a remote system.

    Attributes:
        name: File or directory name (without path).
        path: Absolute path to the file or directory.
        file_type: Type of the file (file, directory, or symlink).
        size: Size in bytes.
        modified_time: Last modification timestamp.
        permissions: Unix permission string (e.g., "rwxr-xr-x").
        owner: File owner username (default: empty).
        group: File group name (default: empty).
        is_hidden: Whether the file is hidden (starts with dot).
    """

    name: str
    path: str
    file_type: FileType
    size: int
    modified_time: datetime
    permissions: str
    owner: str = ""
    group: str = ""
    is_hidden: bool = False

    @property
    def extension(self) -> str:
        """
        Get the file extension.

        Returns:
            File extension (including the dot) or empty string if no extension.
        """
        if self.file_type == FileType.DIRECTORY:
            return ""

        if '.' in self.name:
            return '.' + self.name.rsplit('.', 1)[1].lower()
        return ""

    @property
    def is_gromacs_file(self) -> bool:
        """
        Check if the file is a GROMACS-related file.

        Returns:
            True if the file has a GROMACS-associated extension.
        """
        gromacs_extensions = {
            '.tpr', '.gro', '.pdb', '.top', '.itp', '.mdp',
            '.edr', '.xvg', '.log', '.trr', '.xtc', '.tng',
            '.cpt', '.gro', '.ndx', '.evt'
        }
        return self.extension.lower() in gromacs_extensions

    @property
    def is_gromacs_input(self) -> bool:
        """
        Check if the file is a GROMACS input file.

        Input files are typically used to configure and prepare simulations.

        Returns:
            True if the file is a GROMACS input file type.
        """
        input_extensions = {'.tpr', '.gro', '.pdb', '.top', '.itp', '.mdp', '.ndx'}
        return self.extension.lower() in input_extensions

    @property
    def is_gromacs_output(self) -> bool:
        """
        Check if the file is a GROMACS output file.

        Output files are generated during or after simulation execution.

        Returns:
            True if the file is a GROMACS output file type.
        """
        output_extensions = {'.edr', '.xvg', '.log', '.trr', '.xtc', '.tng', '.cpt', '.evt'}
        return self.extension.lower() in output_extensions

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the FileMetadata to a dictionary representation.

        Returns:
            Dictionary containing all file attributes with FileType enum
            and datetime object converted to string values.
        """
        data = asdict(self)

        # Convert FileType enum to string
        if isinstance(data['file_type'], FileType):
            data['file_type'] = data['file_type'].value

        # Convert datetime to ISO format
        if isinstance(data['modified_time'], datetime):
            data['modified_time'] = data['modified_time'].isoformat()

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FileMetadata':
        """
        Create a FileMetadata instance from a dictionary.

        Args:
            data: Dictionary containing file attributes. FileType values as strings
                  and datetime strings in ISO format are automatically converted.

        Returns:
            A new FileMetadata instance.
        """
        data_copy = data.copy()

        # Convert file_type string to FileType enum
        if isinstance(data_copy.get('file_type'), str):
            data_copy['file_type'] = FileType(data_copy['file_type'])

        # Convert modified_time string to datetime
        if isinstance(data_copy.get('modified_time'), str):
            data_copy['modified_time'] = datetime.fromisoformat(data_copy['modified_time'])

        return cls(**data_copy)

    def format_size(self) -> str:
        """
        Format the file size in human-readable format.

        Returns:
            Human-readable size string (e.g., "1.5 MB", "2.3 GB").
        """
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        size = float(self.size)

        for unit in units:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0

        return f"{size:.1f} PB"

    def format_time(self) -> str:
        """
        Format the modification time in a human-readable format.

        Returns:
            Formatted timestamp string (e.g., "2026-02-28 14:30:45").
        """
        return self.modified_time.strftime("%Y-%m-%d %H:%M:%S")
