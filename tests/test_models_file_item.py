"""Unit tests for transfpro.models.file_item module."""

import unittest
from datetime import datetime

from transfpro.models.file_item import FileType, FileMetadata


class TestFileType(unittest.TestCase):
    """Tests for FileType enum."""

    def test_values(self):
        self.assertEqual(FileType.FILE.value, "file")
        self.assertEqual(FileType.DIRECTORY.value, "directory")
        self.assertEqual(FileType.SYMLINK.value, "symlink")


class TestFileMetadata(unittest.TestCase):
    """Tests for FileMetadata dataclass."""

    def _make(self, **kw):
        defaults = dict(
            name="topology.top",
            path="/home/user/sim/topology.top",
            file_type=FileType.FILE,
            size=4096,
            modified_time=datetime(2026, 3, 1, 12, 0),
            permissions="rw-r--r--",
        )
        defaults.update(kw)
        return FileMetadata(**defaults)

    # ── Extension detection ──

    def test_extension_normal(self):
        f = self._make(name="data.csv")
        self.assertEqual(f.extension, ".csv")

    def test_extension_gromacs(self):
        f = self._make(name="system.tpr")
        self.assertEqual(f.extension, ".tpr")

    def test_extension_case_insensitive(self):
        f = self._make(name="FILE.TPR")
        self.assertEqual(f.extension, ".tpr")

    def test_extension_no_dot(self):
        f = self._make(name="Makefile")
        self.assertEqual(f.extension, "")

    def test_extension_directory(self):
        f = self._make(name="src", file_type=FileType.DIRECTORY)
        self.assertEqual(f.extension, "")

    # ── GROMACS detection ──

    def test_is_gromacs_file_tpr(self):
        f = self._make(name="run.tpr")
        self.assertTrue(f.is_gromacs_file)

    def test_is_gromacs_file_xtc(self):
        f = self._make(name="traj.xtc")
        self.assertTrue(f.is_gromacs_file)

    def test_is_gromacs_file_csv(self):
        f = self._make(name="data.csv")
        self.assertFalse(f.is_gromacs_file)

    def test_is_gromacs_input(self):
        for ext in [".tpr", ".gro", ".pdb", ".top", ".itp", ".mdp", ".ndx"]:
            f = self._make(name=f"file{ext}")
            self.assertTrue(f.is_gromacs_input, f"Expected {ext} to be GROMACS input")

    def test_is_gromacs_output(self):
        for ext in [".edr", ".xvg", ".log", ".trr", ".xtc", ".tng", ".cpt", ".evt"]:
            f = self._make(name=f"file{ext}")
            self.assertTrue(f.is_gromacs_output, f"Expected {ext} to be GROMACS output")

    def test_input_is_not_output(self):
        f = self._make(name="system.tpr")
        self.assertTrue(f.is_gromacs_input)
        self.assertFalse(f.is_gromacs_output)

    # ── Formatting ──

    def test_format_size_bytes(self):
        f = self._make(size=500)
        self.assertEqual(f.format_size(), "500.0 B")

    def test_format_size_kb(self):
        f = self._make(size=2048)
        self.assertEqual(f.format_size(), "2.0 KB")

    def test_format_size_mb(self):
        f = self._make(size=5 * 1024 * 1024)
        self.assertEqual(f.format_size(), "5.0 MB")

    def test_format_size_gb(self):
        f = self._make(size=3 * 1024 * 1024 * 1024)
        self.assertEqual(f.format_size(), "3.0 GB")

    def test_format_time(self):
        f = self._make(modified_time=datetime(2026, 3, 1, 14, 30, 45))
        self.assertEqual(f.format_time(), "2026-03-01 14:30:45")

    # ── Serialization ──

    def test_to_dict(self):
        f = self._make()
        d = f.to_dict()
        self.assertEqual(d["file_type"], "file")
        self.assertEqual(d["name"], "topology.top")
        self.assertIsInstance(d["modified_time"], str)

    def test_roundtrip(self):
        f = self._make(
            name="output.log",
            owner="user1",
            group="research",
            is_hidden=False,
        )
        d = f.to_dict()
        restored = FileMetadata.from_dict(d)
        self.assertEqual(restored.name, f.name)
        self.assertEqual(restored.file_type, f.file_type)
        self.assertEqual(restored.size, f.size)
        self.assertEqual(restored.owner, f.owner)
        self.assertEqual(restored.group, f.group)
        self.assertIsInstance(restored.modified_time, datetime)

    def test_hidden_file(self):
        f = self._make(name=".bashrc", is_hidden=True)
        self.assertTrue(f.is_hidden)


if __name__ == "__main__":
    unittest.main()
