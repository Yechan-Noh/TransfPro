"""Unit tests for transfpro.config.constants module."""

import unittest

from transfpro.config import constants


class TestAppMetadata(unittest.TestCase):
    """Test application metadata constants."""

    def test_app_name(self):
        self.assertEqual(constants.APP_NAME, "TransfPro")

    def test_app_version_format(self):
        parts = constants.APP_VERSION.split(".")
        self.assertEqual(len(parts), 3, "Version must be semver (major.minor.patch)")
        for part in parts:
            self.assertTrue(part.isdigit(), f"Version component '{part}' is not numeric")


class TestSSHConstants(unittest.TestCase):
    """Test SSH-related constants."""

    def test_default_port(self):
        self.assertEqual(constants.SSH_DEFAULT_PORT, 22)

    def test_default_timeout_positive(self):
        self.assertGreater(constants.SSH_DEFAULT_TIMEOUT, 0)

    def test_keepalive_positive(self):
        self.assertGreater(constants.SSH_KEEPALIVE_INTERVAL, 0)


class TestSFTPConstants(unittest.TestCase):
    """Test SFTP performance tuning constants."""

    def test_window_size(self):
        self.assertEqual(constants.SFTP_WINDOW_SIZE, 2 * 1024 * 1024)

    def test_max_packet_size(self):
        self.assertEqual(constants.SFTP_MAX_PACKET_SIZE, 64 * 1024)

    def test_max_read_size(self):
        self.assertEqual(constants.SFTP_MAX_READ_SIZE, 64 * 1024)

    def test_operation_timeout_positive(self):
        self.assertGreater(constants.SFTP_OPERATION_TIMEOUT, 0)

    def test_progress_emit_interval(self):
        self.assertGreater(constants.PROGRESS_EMIT_INTERVAL, 0)
        self.assertLess(constants.PROGRESS_EMIT_INTERVAL, 1.0)


class TestTransferConstants(unittest.TestCase):
    """Test transfer-related constants."""

    def test_chunk_size(self):
        self.assertEqual(constants.TRANSFER_CHUNK_SIZE, 65536)

    def test_max_concurrent(self):
        self.assertGreater(constants.MAX_CONCURRENT_TRANSFERS, 0)

    def test_speed_update_interval(self):
        self.assertGreater(constants.TRANSFER_SPEED_UPDATE_INTERVAL, 0)

    def test_transfer_statuses_complete(self):
        expected = {"pending", "in_progress", "completed", "failed", "cancelled"}
        self.assertEqual(constants.TRANSFER_STATUSES, expected)


class TestSLURMConstants(unittest.TestCase):
    """Test SLURM-related constants."""

    def test_default_cpus_positive(self):
        self.assertGreater(constants.SLURM_DEFAULT_CPUS, 0)

    def test_default_nodes_positive(self):
        self.assertGreater(constants.SLURM_DEFAULT_NODES, 0)

    def test_job_states_contains_running(self):
        self.assertIn("RUNNING", constants.SLURM_JOB_STATES)

    def test_job_states_contains_pending(self):
        self.assertIn("PENDING", constants.SLURM_JOB_STATES)

    def test_job_states_contains_completed(self):
        self.assertIn("COMPLETED", constants.SLURM_JOB_STATES)


class TestUIConstants(unittest.TestCase):
    """Test UI-related constants."""

    def test_default_window_dimensions(self):
        self.assertGreater(constants.DEFAULT_WINDOW_WIDTH, 0)
        self.assertGreater(constants.DEFAULT_WINDOW_HEIGHT, 0)

    def test_min_window_dimensions(self):
        self.assertGreater(constants.MIN_WINDOW_WIDTH, 0)
        self.assertGreater(constants.MIN_WINDOW_HEIGHT, 0)
        self.assertLessEqual(constants.MIN_WINDOW_WIDTH, constants.DEFAULT_WINDOW_WIDTH)
        self.assertLessEqual(constants.MIN_WINDOW_HEIGHT, constants.DEFAULT_WINDOW_HEIGHT)

    def test_job_status_colors_valid_hex(self):
        import re
        hex_pattern = re.compile(r"^#[0-9A-Fa-f]{6}$")
        for state, color in constants.JOB_STATUS_COLORS.items():
            self.assertRegex(color, hex_pattern, f"Invalid color for {state}: {color}")


class TestDatabaseConstants(unittest.TestCase):
    """Test database-related constants."""

    def test_timeout_positive(self):
        self.assertGreater(constants.DATABASE_TIMEOUT, 0)

    def test_max_retries_positive(self):
        self.assertGreater(constants.DATABASE_MAX_RETRIES, 0)


if __name__ == "__main__":
    unittest.main()
