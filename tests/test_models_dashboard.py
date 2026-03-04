"""Unit tests for transfpro.models.dashboard module."""

import unittest
from datetime import datetime

from transfpro.models.dashboard import (
    PartitionInfo,
    ClusterInfo,
    StorageInfo,
    DashboardMetrics,
)
from transfpro.models.job import SimulationProgress


class TestPartitionInfo(unittest.TestCase):
    """Tests for PartitionInfo dataclass."""

    def _make(self, **kw):
        defaults = dict(
            name="gpu",
            state="up",
            total_nodes=20,
            available_nodes=8,
            total_cpus=640,
            max_time="7-00:00:00",
        )
        defaults.update(kw)
        return PartitionInfo(**defaults)

    def test_construction(self):
        p = self._make()
        self.assertEqual(p.name, "gpu")
        self.assertFalse(p.default)

    def test_default_partition(self):
        p = self._make(default=True)
        self.assertTrue(p.default)

    def test_roundtrip(self):
        p = self._make(default=True)
        d = p.to_dict()
        restored = PartitionInfo.from_dict(d)
        self.assertEqual(restored.name, p.name)
        self.assertEqual(restored.total_nodes, p.total_nodes)
        self.assertTrue(restored.default)


class TestClusterInfo(unittest.TestCase):
    """Tests for ClusterInfo dataclass."""

    def test_roundtrip(self):
        ci = ClusterInfo(
            partitions=[
                PartitionInfo("cpu", "up", 50, 30, 1600, "3-00:00:00"),
                PartitionInfo("gpu", "up", 10, 5, 320, "1-00:00:00"),
            ],
            total_nodes=60,
            total_cpus=1920,
            total_gpus=40,
        )
        d = ci.to_dict()
        self.assertEqual(len(d["partitions"]), 2)
        restored = ClusterInfo.from_dict(d)
        self.assertEqual(len(restored.partitions), 2)
        self.assertIsInstance(restored.partitions[0], PartitionInfo)
        self.assertEqual(restored.total_gpus, 40)


class TestStorageInfo(unittest.TestCase):
    """Tests for StorageInfo dataclass."""

    def test_usage_percent(self):
        s = StorageInfo(path="/home", label="Home", used_bytes=500, quota_bytes=1000)
        self.assertAlmostEqual(s.usage_percent, 50.0)

    def test_usage_percent_zero_quota(self):
        s = StorageInfo(path="/home", label="Home", used_bytes=0, quota_bytes=0)
        self.assertAlmostEqual(s.usage_percent, 100.0)

    def test_usage_percent_full(self):
        s = StorageInfo(path="/scratch", label="Scratch", used_bytes=1000, quota_bytes=1000)
        self.assertAlmostEqual(s.usage_percent, 100.0)

    def test_roundtrip(self):
        s = StorageInfo(path="/scratch", label="Scratch", used_bytes=750, quota_bytes=1000)
        d = s.to_dict()
        restored = StorageInfo.from_dict(d)
        self.assertEqual(restored.path, s.path)
        self.assertEqual(restored.used_bytes, s.used_bytes)


class TestDashboardMetrics(unittest.TestCase):
    """Tests for DashboardMetrics dataclass."""

    def test_defaults(self):
        dm = DashboardMetrics()
        self.assertEqual(dm.jobs_running, 0)
        self.assertEqual(dm.jobs_pending, 0)
        self.assertEqual(dm.total_jobs, 0)
        self.assertIsNotNone(dm.timestamp)

    def test_cpu_usage_percent(self):
        dm = DashboardMetrics(total_cpu_available=100, cpu_used=75)
        self.assertAlmostEqual(dm.cpu_usage_percent, 75.0)

    def test_cpu_usage_zero_available(self):
        dm = DashboardMetrics(total_cpu_available=0, cpu_used=0)
        self.assertAlmostEqual(dm.cpu_usage_percent, 0.0)

    def test_memory_usage_percent(self):
        dm = DashboardMetrics(memory_available_gb=64.0, memory_used_gb=16.0)
        # memory_usage = used / (available + used) = 16 / 80 = 20%
        self.assertAlmostEqual(dm.memory_usage_percent, 20.0)

    def test_memory_usage_zero(self):
        dm = DashboardMetrics(memory_available_gb=0.0, memory_used_gb=0.0)
        self.assertAlmostEqual(dm.memory_usage_percent, 0.0)

    def test_total_jobs(self):
        dm = DashboardMetrics(
            jobs_running=5,
            jobs_pending=3,
            jobs_completed=10,
            jobs_failed=2,
        )
        self.assertEqual(dm.total_jobs, 20)

    def test_roundtrip(self):
        now = datetime(2026, 3, 1, 12, 0, 0)
        dm = DashboardMetrics(
            jobs_running=2,
            jobs_pending=1,
            total_cpu_available=100,
            cpu_used=50,
            storage_info=[
                StorageInfo("/home", "Home", 500, 1000),
            ],
            active_simulations=[
                SimulationProgress(
                    "123", "md", 100.0, 200.0, 10.0,
                    50.0, 5.0, 50000, 100000, "06:00:00",
                ),
            ],
            timestamp=now,
        )
        d = dm.to_dict()
        restored = DashboardMetrics.from_dict(d)
        self.assertEqual(restored.jobs_running, 2)
        self.assertEqual(len(restored.storage_info), 1)
        self.assertIsInstance(restored.storage_info[0], StorageInfo)
        self.assertEqual(len(restored.active_simulations), 1)
        self.assertIsInstance(restored.active_simulations[0], SimulationProgress)
        self.assertEqual(restored.timestamp, now)

    def test_to_dict_timestamp_iso(self):
        now = datetime(2026, 3, 1, 12, 0, 0)
        dm = DashboardMetrics(timestamp=now)
        d = dm.to_dict()
        self.assertEqual(d["timestamp"], "2026-03-01T12:00:00")


if __name__ == "__main__":
    unittest.main()
