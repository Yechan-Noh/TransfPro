"""Unit tests for transfpro.models.connection module."""

import unittest
from datetime import datetime

from transfpro.models.connection import ConnectionProfile


class TestConnectionProfileDefaults(unittest.TestCase):
    """Test default values on ConnectionProfile."""

    def test_defaults(self):
        p = ConnectionProfile()
        self.assertEqual(p.name, "")
        self.assertEqual(p.host, "")
        self.assertEqual(p.port, 22)
        self.assertEqual(p.username, "")
        self.assertEqual(p.auth_method, "password")
        self.assertIsNone(p.key_path)
        self.assertFalse(p.has_2fa)
        self.assertEqual(p.two_fa_response, "1")
        self.assertEqual(p.two_fa_timeout, 60)
        self.assertFalse(p.remember_password)
        self.assertEqual(p.timeout, 10)
        self.assertTrue(p.auto_reconnect)
        self.assertEqual(p.keepalive_interval, 30)

    def test_created_at_auto_set(self):
        p = ConnectionProfile()
        self.assertIsNotNone(p.created_at)
        self.assertIsInstance(p.created_at, datetime)

    def test_uuid_generated(self):
        p1 = ConnectionProfile()
        p2 = ConnectionProfile()
        self.assertNotEqual(p1.id, p2.id)
        self.assertEqual(len(p1.id), 36)


class TestConnectionProfileSerialization(unittest.TestCase):
    """Test to_dict / from_dict round-trip."""

    def _make_profile(self, **overrides):
        defaults = dict(
            name="HPC Cluster",
            host="cluster.example.com",
            port=22,
            username="researcher",
            auth_method="password",
            has_2fa=True,
            two_fa_response="1",
            two_fa_timeout=120,
            remember_password=True,
            timeout=15,
            auto_reconnect=False,
            keepalive_interval=45,
        )
        defaults.update(overrides)
        return ConnectionProfile(**defaults)

    def test_to_dict_contains_all_fields(self):
        p = self._make_profile()
        d = p.to_dict()
        self.assertEqual(d["name"], "HPC Cluster")
        self.assertEqual(d["host"], "cluster.example.com")
        self.assertEqual(d["port"], 22)
        self.assertEqual(d["username"], "researcher")
        self.assertTrue(d["has_2fa"])
        self.assertIn("created_at", d)

    def test_to_dict_datetime_iso(self):
        now = datetime(2026, 3, 1, 12, 0, 0)
        p = self._make_profile(created_at=now)
        d = p.to_dict()
        self.assertEqual(d["created_at"], "2026-03-01T12:00:00")

    def test_roundtrip(self):
        p = self._make_profile()
        d = p.to_dict()
        restored = ConnectionProfile.from_dict(d)
        self.assertEqual(restored.name, p.name)
        self.assertEqual(restored.host, p.host)
        self.assertEqual(restored.port, p.port)
        self.assertEqual(restored.username, p.username)
        self.assertEqual(restored.has_2fa, p.has_2fa)
        self.assertEqual(restored.two_fa_response, p.two_fa_response)
        self.assertEqual(restored.two_fa_timeout, p.two_fa_timeout)
        self.assertEqual(restored.remember_password, p.remember_password)
        self.assertEqual(restored.timeout, p.timeout)
        self.assertEqual(restored.auto_reconnect, p.auto_reconnect)
        self.assertEqual(restored.keepalive_interval, p.keepalive_interval)

    def test_from_dict_with_iso_strings(self):
        data = {
            "id": "abc-123",
            "name": "Test",
            "host": "host",
            "port": 2222,
            "username": "user",
            "auth_method": "key",
            "key_path": "/home/user/.ssh/id_rsa",
            "has_2fa": False,
            "two_fa_response": "1",
            "two_fa_timeout": 60,
            "remember_password": False,
            "timeout": 10,
            "auto_reconnect": True,
            "keepalive_interval": 30,
            "created_at": "2025-01-15T09:30:00",
            "last_connected": "2025-02-20T14:00:00",
        }
        p = ConnectionProfile.from_dict(data)
        self.assertEqual(p.id, "abc-123")
        self.assertEqual(p.port, 2222)
        self.assertEqual(p.auth_method, "key")
        self.assertEqual(p.key_path, "/home/user/.ssh/id_rsa")
        self.assertIsInstance(p.created_at, datetime)
        self.assertIsInstance(p.last_connected, datetime)


class TestConnectionProfileCopy(unittest.TestCase):
    """Test copy method."""

    def test_copy_creates_new_id(self):
        p = ConnectionProfile(name="Original", host="host.com")
        c = p.copy()
        self.assertNotEqual(p.id, c.id)
        self.assertEqual(c.name, p.name)
        self.assertEqual(c.host, p.host)

    def test_copy_preserves_all_fields(self):
        p = ConnectionProfile(
            name="X",
            host="h",
            port=2222,
            username="u",
            has_2fa=True,
            timeout=99,
        )
        c = p.copy()
        self.assertEqual(c.port, 2222)
        self.assertEqual(c.username, "u")
        self.assertTrue(c.has_2fa)
        self.assertEqual(c.timeout, 99)


if __name__ == "__main__":
    unittest.main()
