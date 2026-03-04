"""Unit tests for transfpro.models.transfer module."""

import unittest
from datetime import datetime

from transfpro.models.transfer import (
    TransferDirection,
    TransferStatus,
    TransferTask,
)


class TestTransferDirection(unittest.TestCase):
    """Tests for TransferDirection enum."""

    def test_upload_value(self):
        self.assertEqual(TransferDirection.UPLOAD.value, "upload")

    def test_download_value(self):
        self.assertEqual(TransferDirection.DOWNLOAD.value, "download")

    def test_from_string(self):
        self.assertEqual(TransferDirection("upload"), TransferDirection.UPLOAD)
        self.assertEqual(TransferDirection("download"), TransferDirection.DOWNLOAD)

    def test_invalid_value_raises(self):
        with self.assertRaises(ValueError):
            TransferDirection("invalid")


class TestTransferStatus(unittest.TestCase):
    """Tests for TransferStatus enum."""

    def test_all_states_exist(self):
        expected = {"queued", "in_progress", "paused", "completed", "failed", "cancelled"}
        actual = {s.value for s in TransferStatus}
        self.assertEqual(actual, expected)


class TestTransferTask(unittest.TestCase):
    """Tests for TransferTask dataclass."""

    def _make_task(self, **overrides):
        defaults = dict(
            direction=TransferDirection.UPLOAD,
            local_path="/tmp/file.txt",
            remote_path="/home/user/file.txt",
            total_bytes=1000,
        )
        defaults.update(overrides)
        return TransferTask(**defaults)

    # ── Construction ──

    def test_defaults(self):
        task = self._make_task()
        self.assertEqual(task.transferred_bytes, 0)
        self.assertEqual(task.status, TransferStatus.QUEUED)
        self.assertAlmostEqual(task.speed_bps, 0.0)
        self.assertEqual(task.error_message, "")
        self.assertIsNone(task.started_at)
        self.assertIsNone(task.completed_at)

    def test_uuid_generated(self):
        t1 = self._make_task()
        t2 = self._make_task()
        self.assertNotEqual(t1.id, t2.id)
        self.assertEqual(len(t1.id), 36)  # UUID format

    # ── progress_percent ──

    def test_progress_zero(self):
        task = self._make_task(total_bytes=100, transferred_bytes=0)
        self.assertAlmostEqual(task.progress_percent, 0.0)

    def test_progress_half(self):
        task = self._make_task(total_bytes=200, transferred_bytes=100)
        self.assertAlmostEqual(task.progress_percent, 50.0)

    def test_progress_complete(self):
        task = self._make_task(total_bytes=100, transferred_bytes=100)
        self.assertAlmostEqual(task.progress_percent, 100.0)

    def test_progress_zero_total(self):
        """When total_bytes is 0, progress should be 100%."""
        task = self._make_task(total_bytes=0)
        self.assertAlmostEqual(task.progress_percent, 100.0)

    # ── estimated_seconds_remaining ──

    def test_estimated_remaining_normal(self):
        task = self._make_task(total_bytes=1000, transferred_bytes=500)
        task.speed_bps = 100.0
        self.assertAlmostEqual(task.estimated_seconds_remaining, 5.0)

    def test_estimated_remaining_zero_speed(self):
        task = self._make_task(total_bytes=1000)
        task.speed_bps = 0.0
        self.assertAlmostEqual(task.estimated_seconds_remaining, 0.0)

    def test_estimated_remaining_transfer_done(self):
        task = self._make_task(total_bytes=100, transferred_bytes=100)
        task.speed_bps = 50.0
        self.assertAlmostEqual(task.estimated_seconds_remaining, 0.0)

    # ── is_active ──

    def test_is_active_queued(self):
        task = self._make_task(status=TransferStatus.QUEUED)
        self.assertTrue(task.is_active)

    def test_is_active_in_progress(self):
        task = self._make_task(status=TransferStatus.IN_PROGRESS)
        self.assertTrue(task.is_active)

    def test_is_active_completed(self):
        task = self._make_task(status=TransferStatus.COMPLETED)
        self.assertFalse(task.is_active)

    def test_is_active_failed(self):
        task = self._make_task(status=TransferStatus.FAILED)
        self.assertFalse(task.is_active)

    def test_is_active_cancelled(self):
        task = self._make_task(status=TransferStatus.CANCELLED)
        self.assertFalse(task.is_active)

    # ── Serialization ──

    def test_to_dict(self):
        now = datetime.now()
        task = self._make_task(
            total_bytes=500,
            transferred_bytes=250,
            status=TransferStatus.IN_PROGRESS,
            started_at=now,
        )
        d = task.to_dict()
        self.assertEqual(d["direction"], "upload")
        self.assertEqual(d["status"], "in_progress")
        self.assertEqual(d["total_bytes"], 500)
        self.assertEqual(d["transferred_bytes"], 250)
        self.assertEqual(d["started_at"], now.isoformat())
        self.assertIsNone(d["completed_at"])

    def test_roundtrip(self):
        now = datetime.now()
        task = self._make_task(
            total_bytes=1024,
            transferred_bytes=512,
            status=TransferStatus.COMPLETED,
            started_at=now,
            completed_at=now,
        )
        d = task.to_dict()
        restored = TransferTask.from_dict(d)

        self.assertEqual(restored.direction, task.direction)
        self.assertEqual(restored.status, task.status)
        self.assertEqual(restored.local_path, task.local_path)
        self.assertEqual(restored.remote_path, task.remote_path)
        self.assertEqual(restored.total_bytes, task.total_bytes)
        self.assertEqual(restored.transferred_bytes, task.transferred_bytes)

    def test_from_dict_with_raw_values(self):
        data = {
            "id": "test-id",
            "direction": "download",
            "local_path": "/tmp/file.dat",
            "remote_path": "/data/file.dat",
            "total_bytes": 2048,
            "transferred_bytes": 1024,
            "status": "failed",
            "speed_bps": 0.0,
            "error_message": "disk full",
            "started_at": None,
            "completed_at": None,
        }
        task = TransferTask.from_dict(data)
        self.assertEqual(task.direction, TransferDirection.DOWNLOAD)
        self.assertEqual(task.status, TransferStatus.FAILED)
        self.assertEqual(task.error_message, "disk full")


class TestTransferStatusTransitions(unittest.TestCase):
    """Test that status transitions make sense."""

    def test_queued_to_in_progress(self):
        task = TransferTask(
            direction=TransferDirection.UPLOAD,
            local_path="/a",
            remote_path="/b",
            total_bytes=100,
        )
        self.assertEqual(task.status, TransferStatus.QUEUED)
        task.status = TransferStatus.IN_PROGRESS
        self.assertEqual(task.status, TransferStatus.IN_PROGRESS)

    def test_in_progress_to_completed(self):
        task = TransferTask(
            direction=TransferDirection.DOWNLOAD,
            local_path="/a",
            remote_path="/b",
            total_bytes=100,
            status=TransferStatus.IN_PROGRESS,
        )
        task.status = TransferStatus.COMPLETED
        self.assertFalse(task.is_active)


if __name__ == "__main__":
    unittest.main()
