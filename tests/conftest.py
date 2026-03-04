"""Pytest configuration and shared fixtures for TransfPro tests."""

import os
import sys
import tempfile

import pytest

# Ensure the transfpro package is importable even when running tests
# from the project root (e.g., `python -m pytest tests/`)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def tmp_db_path(tmp_path):
    """Return a temporary database path."""
    return str(tmp_path / "test_transfpro.db")


@pytest.fixture
def tmp_dir():
    """Provide a temporary directory that is cleaned up after the test."""
    d = tempfile.mkdtemp(prefix="transfpro_test_")
    yield d
    # Cleanup
    import shutil
    shutil.rmtree(d, ignore_errors=True)
