"""Unit tests for transfpro.utils.exceptions module."""

import unittest

from transfpro.utils.exceptions import (
    TransfProException,
    SSHConnectionError,
    SSHAuthenticationError,
    SSH2FAError,
    SFTPError,
    SFTPTransferError,
    SLURMError,
    JobSubmissionError,
    JobStatusError,
    JobCancellationError,
    DatabaseError,
    DatabaseConnectionError,
    DatabaseQueryError,
    DatabaseIntegrityError,
    GromacsParseError,
    GromacsExecutionError,
    ConfigurationError,
    ValidationError,
)


class TestExceptionHierarchy(unittest.TestCase):
    """Test that exception hierarchy is correct."""

    def test_base_exception(self):
        e = TransfProException("test", error_code=99)
        self.assertEqual(e.message, "test")
        self.assertEqual(e.error_code, 99)
        self.assertIn("TransfProException", str(e))
        self.assertIn("test", str(e))

    def test_ssh_connection_error(self):
        e = SSHConnectionError("timeout", hostname="host.com", port=22)
        self.assertIsInstance(e, TransfProException)
        self.assertEqual(e.hostname, "host.com")
        self.assertEqual(e.port, 22)
        self.assertEqual(e.error_code, 1001)

    def test_ssh_auth_error(self):
        e = SSHAuthenticationError("bad password", auth_method="key", username="user")
        self.assertIsInstance(e, TransfProException)
        self.assertEqual(e.auth_method, "key")
        self.assertEqual(e.username, "user")
        self.assertEqual(e.error_code, 1002)

    def test_ssh_2fa_error(self):
        e = SSH2FAError("2FA timeout", max_attempts=5)
        self.assertIsInstance(e, TransfProException)
        self.assertEqual(e.max_attempts, 5)
        self.assertEqual(e.error_code, 1003)

    def test_sftp_error(self):
        e = SFTPError("permission denied", sftp_error_code=3)
        self.assertIsInstance(e, TransfProException)
        self.assertEqual(e.sftp_error_code, 3)
        self.assertEqual(e.error_code, 2001)

    def test_sftp_transfer_error(self):
        e = SFTPTransferError(
            "disk full",
            local_path="/tmp/f",
            remote_path="/data/f",
            bytes_transferred=1024,
        )
        self.assertIsInstance(e, SFTPError)
        self.assertIsInstance(e, TransfProException)
        self.assertEqual(e.local_path, "/tmp/f")
        self.assertEqual(e.bytes_transferred, 1024)
        self.assertEqual(e.error_code, 2002)

    def test_slurm_error(self):
        e = SLURMError("command failed", slurm_error_code=1)
        self.assertIsInstance(e, TransfProException)
        self.assertEqual(e.slurm_error_code, 1)

    def test_job_submission_error(self):
        e = JobSubmissionError(
            "no resources",
            job_name="md_run",
            partition="gpu",
            reason="QOSMaxNodePerJobLimit",
        )
        self.assertIsInstance(e, SLURMError)
        self.assertEqual(e.job_name, "md_run")
        self.assertEqual(e.partition, "gpu")
        self.assertEqual(e.reason, "QOSMaxNodePerJobLimit")
        self.assertEqual(e.error_code, 3002)

    def test_job_status_error(self):
        e = JobStatusError("not found", job_id="99999")
        self.assertIsInstance(e, SLURMError)
        self.assertEqual(e.job_id, "99999")

    def test_job_cancellation_error(self):
        e = JobCancellationError("permission denied", job_id="88888")
        self.assertIsInstance(e, SLURMError)
        self.assertEqual(e.job_id, "88888")

    def test_database_error(self):
        e = DatabaseError("locked", operation="insert")
        self.assertIsInstance(e, TransfProException)
        self.assertEqual(e.operation, "insert")

    def test_database_connection_error(self):
        e = DatabaseConnectionError("timeout", database_url="sqlite:///test.db")
        self.assertIsInstance(e, DatabaseError)
        self.assertEqual(e.database_url, "sqlite:///test.db")
        self.assertEqual(e.error_code, 4002)

    def test_database_query_error(self):
        e = DatabaseQueryError("syntax error", query="SELECT * FORM x")
        self.assertIsInstance(e, DatabaseError)
        self.assertEqual(e.query, "SELECT * FORM x")

    def test_database_integrity_error(self):
        e = DatabaseIntegrityError("duplicate", constraint="UNIQUE(name)")
        self.assertIsInstance(e, DatabaseError)
        self.assertEqual(e.constraint, "UNIQUE(name)")

    def test_gromacs_parse_error(self):
        e = GromacsParseError("bad format", file_path="/f.gro", file_type=".gro")
        self.assertIsInstance(e, TransfProException)
        self.assertEqual(e.file_path, "/f.gro")
        self.assertEqual(e.file_type, ".gro")

    def test_gromacs_execution_error(self):
        e = GromacsExecutionError("segfault", command="gmx mdrun", return_code=139)
        self.assertIsInstance(e, TransfProException)
        self.assertEqual(e.command, "gmx mdrun")
        self.assertEqual(e.return_code, 139)

    def test_configuration_error(self):
        e = ConfigurationError("missing", config_key="ssh_timeout")
        self.assertIsInstance(e, TransfProException)
        self.assertEqual(e.config_key, "ssh_timeout")

    def test_validation_error(self):
        e = ValidationError("invalid hostname", field="host", value="!!bad!!")
        self.assertIsInstance(e, TransfProException)
        self.assertEqual(e.field, "host")
        self.assertEqual(e.value, "!!bad!!")


class TestExceptionCatchAll(unittest.TestCase):
    """Test that all exceptions can be caught via base class."""

    def test_catch_all(self):
        exceptions = [
            SSHConnectionError("a"),
            SSHAuthenticationError("b"),
            SSH2FAError("c"),
            SFTPError("d"),
            SFTPTransferError("e"),
            SLURMError("f"),
            JobSubmissionError("g"),
            JobStatusError("h"),
            JobCancellationError("i"),
            DatabaseError("j"),
            DatabaseConnectionError("k"),
            DatabaseQueryError("l"),
            DatabaseIntegrityError("m"),
            GromacsParseError("n"),
            GromacsExecutionError("o"),
            ConfigurationError("p"),
            ValidationError("q"),
        ]
        for exc in exceptions:
            with self.assertRaises(TransfProException):
                raise exc


if __name__ == "__main__":
    unittest.main()
