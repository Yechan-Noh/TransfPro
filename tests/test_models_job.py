"""Unit tests for transfpro.models.job module."""

import unittest
from datetime import datetime

from transfpro.models.job import JobState, JobInfo, SimulationProgress


class TestJobState(unittest.TestCase):
    """Tests for JobState enum."""

    def test_all_states(self):
        expected = {
            "PENDING", "RUNNING", "COMPLETED", "FAILED",
            "CANCELLED", "TIMEOUT", "NODE_FAIL", "UNKNOWN",
        }
        actual = {s.value for s in JobState}
        self.assertEqual(actual, expected)

    def test_from_string(self):
        self.assertEqual(JobState("RUNNING"), JobState.RUNNING)

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            JobState("INVALID")


class TestJobInfo(unittest.TestCase):
    """Tests for JobInfo dataclass."""

    def _make_job(self, **overrides):
        defaults = dict(
            job_id="12345",
            name="md_run",
            state=JobState.RUNNING,
            user="researcher",
            partition="gpu",
            nodes=2,
            cpus=64,
            mem_per_node="128G",
            time_limit="24:00:00",
            time_used="01:30:00",
            submit_time=datetime(2026, 3, 1, 8, 0),
            start_time=datetime(2026, 3, 1, 8, 5),
            end_time=None,
        )
        defaults.update(overrides)
        return JobInfo(**defaults)

    def test_is_active_running(self):
        job = self._make_job(state=JobState.RUNNING)
        self.assertTrue(job.is_active())

    def test_is_active_pending(self):
        job = self._make_job(state=JobState.PENDING)
        self.assertTrue(job.is_active())

    def test_is_active_completed(self):
        job = self._make_job(state=JobState.COMPLETED)
        self.assertFalse(job.is_active())

    def test_is_active_failed(self):
        job = self._make_job(state=JobState.FAILED)
        self.assertFalse(job.is_active())

    def test_is_gromacs_job_with_tpr(self):
        job = self._make_job(tpr_file="/scratch/md.tpr")
        self.assertTrue(job.is_gromacs_job())

    def test_is_gromacs_job_with_log(self):
        job = self._make_job(log_file="/scratch/md.log")
        self.assertTrue(job.is_gromacs_job())

    def test_is_gromacs_job_without_files(self):
        job = self._make_job()
        self.assertFalse(job.is_gromacs_job())

    # ── Serialization ──

    def test_to_dict(self):
        job = self._make_job()
        d = job.to_dict()
        self.assertEqual(d["job_id"], "12345")
        self.assertEqual(d["state"], "RUNNING")
        self.assertEqual(d["submit_time"], "2026-03-01T08:00:00")
        self.assertIsNone(d["end_time"])

    def test_roundtrip(self):
        job = self._make_job(
            end_time=datetime(2026, 3, 1, 10, 0),
            tpr_file="/scratch/md.tpr",
            progress_percent=45.5,
            ns_per_day=12.3,
        )
        d = job.to_dict()
        restored = JobInfo.from_dict(d)
        self.assertEqual(restored.job_id, job.job_id)
        self.assertEqual(restored.state, job.state)
        self.assertEqual(restored.tpr_file, job.tpr_file)
        self.assertAlmostEqual(restored.progress_percent, 45.5)
        self.assertAlmostEqual(restored.ns_per_day, 12.3)
        self.assertIsInstance(restored.end_time, datetime)

    def test_from_dict_string_state(self):
        data = {
            "job_id": "99",
            "name": "test",
            "state": "COMPLETED",
            "user": "u",
            "partition": "p",
            "nodes": 1,
            "cpus": 4,
            "mem_per_node": "4G",
            "time_limit": "01:00:00",
            "time_used": "00:30:00",
            "submit_time": None,
            "start_time": None,
            "end_time": None,
        }
        job = JobInfo.from_dict(data)
        self.assertEqual(job.state, JobState.COMPLETED)


class TestSimulationProgress(unittest.TestCase):
    """Tests for SimulationProgress dataclass."""

    def _make_progress(self, **overrides):
        defaults = dict(
            job_id="12345",
            job_name="md_run",
            current_time_ps=500.0,
            total_time_ps=1000.0,
            ns_per_day=15.0,
            percent_complete=50.0,
            estimated_hours_remaining=2.5,
            current_step=500000,
            total_steps=1000000,
            wall_time_used="12:00:00",
        )
        defaults.update(overrides)
        return SimulationProgress(**defaults)

    def test_construction(self):
        sp = self._make_progress()
        self.assertEqual(sp.job_id, "12345")
        self.assertAlmostEqual(sp.percent_complete, 50.0)

    def test_to_dict(self):
        sp = self._make_progress()
        d = sp.to_dict()
        self.assertEqual(d["job_id"], "12345")
        self.assertAlmostEqual(d["ns_per_day"], 15.0)

    def test_roundtrip(self):
        sp = self._make_progress()
        d = sp.to_dict()
        restored = SimulationProgress.from_dict(d)
        self.assertEqual(restored.job_id, sp.job_id)
        self.assertAlmostEqual(restored.current_time_ps, sp.current_time_ps)
        self.assertEqual(restored.current_step, sp.current_step)


if __name__ == "__main__":
    unittest.main()
