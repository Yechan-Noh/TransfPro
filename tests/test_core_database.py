"""Unit tests for transfpro.core.database module."""

import os
import sqlite3
import tempfile
import unittest

from transfpro.core.database import Database


class TestDatabaseInit(unittest.TestCase):
    """Test database initialization and cleanup."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")

    def tearDown(self):
        # Clean up temp files
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        wal = self.db_path + "-wal"
        shm = self.db_path + "-shm"
        if os.path.exists(wal):
            os.remove(wal)
        if os.path.exists(shm):
            os.remove(shm)
        os.rmdir(self.tmpdir)

    def test_creates_database_file(self):
        db = Database(self.db_path)
        self.assertTrue(os.path.exists(self.db_path))
        db.close()

    def test_file_permissions(self):
        db = Database(self.db_path)
        mode = os.stat(self.db_path).st_mode & 0o777
        self.assertEqual(mode, 0o600)
        db.close()

    def test_close(self):
        db = Database(self.db_path)
        db.close()
        self.assertIsNone(db.connection)

    def test_close_idempotent(self):
        db = Database(self.db_path)
        db.close()
        db.close()  # Should not raise
        self.assertIsNone(db.connection)

    def test_cursor_after_close_raises(self):
        db = Database(self.db_path)
        db.close()
        with self.assertRaises(sqlite3.OperationalError):
            db._cursor()

    def test_tables_created(self):
        db = Database(self.db_path)
        cursor = db._cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row["name"] for row in cursor.fetchall()}
        expected = {
            "connection_profiles",
            "jobs",
            "job_templates",
            "transfers",
            "bookmarks",
            "notifications",
        }
        self.assertTrue(expected.issubset(tables), f"Missing tables: {expected - tables}")
        db.close()


class TestDatabaseProfiles(unittest.TestCase):
    """Test connection profile CRUD."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.db = Database(self.db_path)

    def tearDown(self):
        self.db.close()
        for ext in ["", "-wal", "-shm"]:
            p = self.db_path + ext
            if os.path.exists(p):
                os.remove(p)
        os.rmdir(self.tmpdir)

    def _make_profile(self, **kw):
        """Create a simple profile-like object."""

        class P:
            pass

        p = P()
        p.id = kw.get("id", "test-id-1")
        p.name = kw.get("name", "Test Cluster")
        p.host = kw.get("host", "cluster.example.com")
        p.port = kw.get("port", 22)
        p.username = kw.get("username", "testuser")
        p.auth_method = kw.get("auth_method", "password")
        p.key_path = kw.get("key_path", None)
        p.has_2fa = kw.get("has_2fa", False)
        p.two_fa_response = kw.get("two_fa_response", "1")
        p.two_fa_timeout = kw.get("two_fa_timeout", 60)
        p.keepalive_interval = kw.get("keepalive_interval", 30)
        return p

    def test_save_and_get_profile(self):
        p = self._make_profile()
        pid = self.db.save_profile(p)
        self.assertEqual(pid, "test-id-1")

        result = self.db.get_profile("test-id-1")
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Test Cluster")
        self.assertEqual(result["hostname"], "cluster.example.com")
        self.assertEqual(result["port"], 22)

    def test_get_nonexistent_profile(self):
        result = self.db.get_profile("nonexistent")
        self.assertIsNone(result)

    def test_get_all_profiles(self):
        self.db.save_profile(self._make_profile(id="a", name="A", host="a.com"))
        self.db.save_profile(self._make_profile(id="b", name="B", host="b.com"))
        profiles = self.db.get_all_profiles()
        self.assertEqual(len(profiles), 2)

    def test_delete_profile(self):
        self.db.save_profile(self._make_profile(id="del-me"))
        result = self.db.delete_profile("del-me")
        self.assertTrue(result)
        self.assertIsNone(self.db.get_profile("del-me"))

    def test_update_last_connected(self):
        self.db.save_profile(self._make_profile())
        self.db.update_last_connected("test-id-1")
        result = self.db.get_profile("test-id-1")
        self.assertIsNotNone(result["last_connected"])


class TestDatabaseTemplates(unittest.TestCase):
    """Test job template CRUD."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.db = Database(self.db_path)

    def tearDown(self):
        self.db.close()
        for ext in ["", "-wal", "-shm"]:
            p = self.db_path + ext
            if os.path.exists(p):
                os.remove(p)
        os.rmdir(self.tmpdir)

    def test_save_and_get_template(self):
        tid = self.db.save_template(
            name="MD Production",
            description="Standard MD production run",
            workflow_type="gromacs",
            script="#!/bin/bash\ngmx mdrun -s run.tpr",
        )
        self.assertIsNotNone(tid)

        templates = self.db.get_all_templates()
        self.assertEqual(len(templates), 1)
        self.assertEqual(templates[0]["name"], "MD Production")

    def test_delete_template(self):
        tid = self.db.save_template("T", "D", "w", "s")
        result = self.db.delete_template(str(tid))
        self.assertTrue(result)
        self.assertEqual(len(self.db.get_all_templates()), 0)


class TestDatabaseBookmarks(unittest.TestCase):
    """Test bookmark CRUD."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.db = Database(self.db_path)
        # Create a profile for foreign key
        class P:
            id = "conn-1"
            name = "C"
            host = "h"
            port = 22
            username = "u"
            auth_method = "password"
            key_path = None
            has_2fa = False
            two_fa_response = "1"
            two_fa_timeout = 60
            keepalive_interval = 30
        self.db.save_profile(P())

    def tearDown(self):
        self.db.close()
        for ext in ["", "-wal", "-shm"]:
            p = self.db_path + ext
            if os.path.exists(p):
                os.remove(p)
        os.rmdir(self.tmpdir)

    def test_save_and_get_bookmarks(self):
        self.db.save_bookmark("conn-1", "/home/user", "Home")
        self.db.save_bookmark("conn-1", "/scratch", "Scratch")
        bookmarks = self.db.get_bookmarks("conn-1")
        self.assertEqual(len(bookmarks), 2)

    def test_delete_bookmark(self):
        bid = self.db.save_bookmark("conn-1", "/tmp", "Temp")
        self.db.delete_bookmark(str(bid))
        bookmarks = self.db.get_bookmarks("conn-1")
        self.assertEqual(len(bookmarks), 0)


class TestDatabaseNotifications(unittest.TestCase):
    """Test notification CRUD."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.db = Database(self.db_path)

    def tearDown(self):
        self.db.close()
        for ext in ["", "-wal", "-shm"]:
            p = self.db_path + ext
            if os.path.exists(p):
                os.remove(p)
        os.rmdir(self.tmpdir)

    def test_save_and_get_notification(self):
        nid = self.db.save_notification("job_completed", "Job 123 finished", "123")
        self.assertIsNotNone(nid)
        notifications = self.db.get_notifications()
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]["message"], "Job 123 finished")

    def test_mark_notification_read(self):
        nid = self.db.save_notification("job_failed", "Job 456 failed")
        self.db.mark_notification_read(str(nid))
        notifications = self.db.get_notifications()
        self.assertEqual(notifications[0]["is_read"], 1)


if __name__ == "__main__":
    unittest.main()
