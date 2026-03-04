"""SQLite database for persistent data storage."""

import logging
import sqlite3
import os
import json
from typing import Optional, List, Dict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class Database:
    """SQLite database for TransfPro persistent data."""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize database connection.

        Creates default database path if not specified:
        ~/.transfpro/transfpro.db

        Args:
            db_path: Optional custom database path
        """
        if db_path is None:
            # Default path
            transfpro_dir = Path.home() / ".transfpro"
            transfpro_dir.mkdir(parents=True, exist_ok=True)
            # Restrict config directory to owner only
            try:
                os.chmod(str(transfpro_dir), 0o700)
            except OSError:
                pass
            db_path = str(transfpro_dir / "transfpro.db")

        self.db_path = db_path
        self.connection = None

        logger.debug(f"Initializing database")
        self._init_connection()
        try:
            self._create_tables()
        except Exception:
            # Close connection if table creation fails to avoid leaks
            self.close()
            raise

        # Restrict database file to owner only
        try:
            os.chmod(self.db_path, 0o600)
        except OSError:
            pass

    def __del__(self):
        """Ensure database connection is closed on garbage collection."""
        self.close()

    def _ensure_connection(self):
        """Ensure database connection is valid, raising if not."""
        if self.connection is None:
            raise sqlite3.OperationalError("Database connection is not initialized")

    def _cursor(self):
        """Get a database cursor, ensuring connection is valid first."""
        self._ensure_connection()
        return self.connection.cursor()

    def _init_connection(self):
        """Initialize database connection."""
        try:
            self.connection = sqlite3.connect(self.db_path)
            self.connection.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrent read performance
            self.connection.execute("PRAGMA journal_mode=WAL")
            logger.debug(f"Connected to database: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def _create_tables(self):
        """Create database tables if they don't exist."""
        try:
            cursor = self._cursor()

            # Connection profiles table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS connection_profiles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    hostname TEXT NOT NULL,
                    port INTEGER DEFAULT 22,
                    username TEXT,
                    has_2fa BOOLEAN DEFAULT 0,
                    two_fa_response TEXT DEFAULT '1',
                    two_fa_timeout INTEGER DEFAULT 60,
                    use_key BOOLEAN DEFAULT 0,
                    key_path TEXT,
                    keep_alive_interval INTEGER DEFAULT 30,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_connected TIMESTAMP,
                    UNIQUE(hostname, port, username)
                )
            """)

            # Migration: drop password column from old schema
            # SQLite doesn't support DROP COLUMN before 3.35.0,
            # so we just ignore the column if it exists.
            try:
                cursor.execute(
                    "SELECT password FROM connection_profiles LIMIT 0"
                )
                # Column exists — create new table without it
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS connection_profiles_new (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        hostname TEXT NOT NULL,
                        port INTEGER DEFAULT 22,
                        username TEXT,
                        has_2fa BOOLEAN DEFAULT 0,
                        two_fa_response TEXT DEFAULT '1',
                        two_fa_timeout INTEGER DEFAULT 60,
                        use_key BOOLEAN DEFAULT 0,
                        key_path TEXT,
                        keep_alive_interval INTEGER DEFAULT 30,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_connected TIMESTAMP,
                        UNIQUE(hostname, port, username)
                    )
                """)
                cursor.execute("""
                    INSERT OR IGNORE INTO connection_profiles_new
                    (id, name, hostname, port, username, has_2fa,
                     two_fa_response, two_fa_timeout, use_key, key_path,
                     keep_alive_interval, created_at, last_connected)
                    SELECT id, name, hostname, port, username, has_2fa,
                           two_fa_response, two_fa_timeout, use_key, key_path,
                           keep_alive_interval, created_at, last_connected
                    FROM connection_profiles
                """)
                cursor.execute("DROP TABLE connection_profiles")
                cursor.execute(
                    "ALTER TABLE connection_profiles_new "
                    "RENAME TO connection_profiles"
                )
                logger.info("Migrated connection_profiles: removed password column")
            except sqlite3.OperationalError:
                pass  # password column doesn't exist — already migrated

            # Job history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    connection_id TEXT NOT NULL,
                    name TEXT,
                    user TEXT,
                    state TEXT,
                    queue TEXT,
                    nodes INTEGER,
                    cpus INTEGER,
                    memory_gb REAL,
                    time_limit TEXT,
                    elapsed TEXT,
                    start_time TIMESTAMP,
                    end_time TIMESTAMP,
                    exit_code INTEGER,
                    node_list TEXT,
                    metadata TEXT,
                    saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(connection_id) REFERENCES connection_profiles(id),
                    UNIQUE(job_id, connection_id)
                )
            """)

            # Job templates table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS job_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    workflow_type TEXT,
                    script TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # File transfer history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transfers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    connection_id TEXT NOT NULL,
                    transfer_type TEXT,
                    local_path TEXT,
                    remote_path TEXT,
                    file_size INTEGER,
                    bytes_transferred INTEGER,
                    status TEXT,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    error_message TEXT,
                    FOREIGN KEY(connection_id) REFERENCES connection_profiles(id)
                )
            """)

            # Bookmarks table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    connection_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    label TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(connection_id) REFERENCES connection_profiles(id),
                    UNIQUE(connection_id, path)
                )
            """)

            # Notifications table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    notification_type TEXT,
                    message TEXT NOT NULL,
                    job_id TEXT,
                    is_read BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            self.connection.commit()
            logger.debug("Database tables created/verified")

        except sqlite3.Error as e:
            logger.error(f"Failed to create tables: {e}")
            raise

    def close(self):
        """Close database connection."""
        if self.connection:
            try:
                self.connection.close()
            except Exception as e:
                logger.debug(f"Error closing database: {e}")
            self.connection = None
            logger.debug("Database connection closed")

    # Connection Profile Methods

    def save_profile(self, profile) -> str:
        """
        Save or update connection profile.

        Args:
            profile: ConnectionProfile object

        Returns:
            Profile ID
        """
        try:
            cursor = self._cursor()

            # Map ConnectionProfile fields to database columns
            use_key = (profile.auth_method == "key") if hasattr(profile, 'auth_method') else getattr(profile, 'use_key', False)
            hostname = getattr(profile, 'host', None) or getattr(profile, 'hostname', '')
            keep_alive = getattr(profile, 'keepalive_interval', None) or getattr(profile, 'keep_alive_interval', 30)

            cursor.execute("""
                INSERT OR REPLACE INTO connection_profiles
                (id, name, hostname, port, username, has_2fa,
                 two_fa_response, two_fa_timeout, use_key, key_path, keep_alive_interval)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                profile.id,
                profile.name,
                hostname,
                profile.port,
                profile.username,
                profile.has_2fa,
                profile.two_fa_response,
                profile.two_fa_timeout,
                use_key,
                profile.key_path,
                keep_alive,
            ))

            self.connection.commit()
            logger.info(f"Saved profile: {profile.id}")
            return profile.id

        except sqlite3.Error as e:
            logger.error(f"Failed to save profile: {e}")
            raise

    def get_profile(self, profile_id: str) -> Optional[Dict]:
        """
        Retrieve connection profile.

        Args:
            profile_id: Profile ID

        Returns:
            Profile dictionary or None if not found
        """
        try:
            cursor = self._cursor()
            cursor.execute(
                "SELECT * FROM connection_profiles WHERE id = ?",
                (profile_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

        except sqlite3.Error as e:
            logger.error(f"Failed to get profile: {e}")
            raise

    def get_all_profiles(self) -> List[Dict]:
        """
        Retrieve all connection profiles.

        Returns:
            List of profile dictionaries
        """
        try:
            cursor = self._cursor()
            cursor.execute(
                "SELECT * FROM connection_profiles ORDER BY last_connected DESC"
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Failed to get profiles: {e}")
            raise

    def delete_profile(self, profile_id: str) -> bool:
        """
        Delete connection profile.

        Args:
            profile_id: Profile ID

        Returns:
            True if successful
        """
        try:
            cursor = self._cursor()
            cursor.execute(
                "DELETE FROM connection_profiles WHERE id = ?",
                (profile_id,)
            )
            self.connection.commit()
            logger.info(f"Deleted profile: {profile_id}")
            return True

        except sqlite3.Error as e:
            logger.error(f"Failed to delete profile: {e}")
            raise

    def update_last_connected(self, profile_id: str):
        """
        Update last connected timestamp for profile.

        Args:
            profile_id: Profile ID
        """
        try:
            cursor = self._cursor()
            cursor.execute(
                "UPDATE connection_profiles SET last_connected = CURRENT_TIMESTAMP WHERE id = ?",
                (profile_id,)
            )
            self.connection.commit()
            logger.debug(f"Updated last_connected for profile: {profile_id}")

        except sqlite3.Error as e:
            logger.error(f"Failed to update last_connected: {e}")

    # Job History Methods

    def save_job(self, job, connection_id: str):
        """
        Save job information.

        Args:
            job: JobInfo object
            connection_id: Connection profile ID
        """
        try:
            cursor = self._cursor()

            metadata = json.dumps(job.metadata) if job.metadata else "{}"

            cursor.execute("""
                INSERT OR REPLACE INTO jobs
                (job_id, connection_id, name, user, state, queue, nodes, cpus, memory_gb,
                 time_limit, elapsed, start_time, end_time, exit_code, node_list, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.job_id,
                connection_id,
                job.name,
                job.user,
                job.state,
                job.queue,
                job.nodes,
                job.cpus,
                job.memory_gb,
                job.time_limit,
                job.elapsed,
                job.start_time,
                job.end_time,
                job.exit_code,
                job.node_list,
                metadata
            ))

            self.connection.commit()
            logger.debug(f"Saved job: {job.job_id}")

        except sqlite3.Error as e:
            logger.error(f"Failed to save job: {e}")

    def get_job_history(self, connection_id: str, limit: int = 100) -> List[Dict]:
        """
        Retrieve job history for a connection.

        Args:
            connection_id: Connection profile ID
            limit: Maximum number of jobs to retrieve

        Returns:
            List of job dictionaries
        """
        try:
            cursor = self._cursor()
            cursor.execute(
                "SELECT * FROM jobs WHERE connection_id = ? "
                "ORDER BY start_time DESC LIMIT ?",
                (connection_id, limit)
            )
            rows = cursor.fetchall()
            jobs = []
            for row in rows:
                job_dict = dict(row)
                # Parse metadata JSON
                if job_dict.get('metadata'):
                    job_dict['metadata'] = json.loads(job_dict['metadata'])
                jobs.append(job_dict)
            return jobs

        except sqlite3.Error as e:
            logger.error(f"Failed to get job history: {e}")
            return []

    def get_job_stats(self, connection_id: str, days: int = 30) -> Dict:
        """
        Get job statistics for a connection.

        Args:
            connection_id: Connection profile ID
            days: Number of days to analyze

        Returns:
            Dictionary with statistics
        """
        try:
            cursor = self._cursor()

            # Get stats for recent jobs
            cursor.execute("""
                SELECT COUNT(*) as total, state,
                       SUM(CASE WHEN state = 'COMPLETED' THEN 1 ELSE 0 END) as completed,
                       SUM(CASE WHEN state = 'FAILED' THEN 1 ELSE 0 END) as failed,
                       SUM(CASE WHEN state = 'CANCELLED' THEN 1 ELSE 0 END) as cancelled,
                       AVG(cpus) as avg_cpus, AVG(memory_gb) as avg_memory
                FROM jobs
                WHERE connection_id = ?
                AND saved_at > datetime('now', ? || ' days')
                GROUP BY state
            """, (connection_id, -days))

            rows = cursor.fetchall()
            stats = {
                'total': 0,
                'completed': 0,
                'failed': 0,
                'cancelled': 0,
                'avg_cpus': 0,
                'avg_memory_gb': 0
            }

            for row in rows:
                row_dict = dict(row)
                stats['total'] += row_dict.get('total', 0)
                stats['completed'] += row_dict.get('completed', 0) or 0
                stats['failed'] += row_dict.get('failed', 0) or 0
                stats['cancelled'] += row_dict.get('cancelled', 0) or 0

            return stats

        except sqlite3.Error as e:
            logger.error(f"Failed to get job stats: {e}")
            return {}

    # Job Template Methods

    def save_template(self, name: str, description: str, workflow_type: str, script: str) -> int:
        """
        Save job template.

        Args:
            name: Template name
            description: Template description
            workflow_type: Workflow type identifier
            script: Template script content

        Returns:
            Template ID
        """
        try:
            cursor = self._cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO job_templates
                (name, description, workflow_type, script, last_modified)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (name, description, workflow_type, script))

            self.connection.commit()
            logger.info(f"Saved template: {name}")
            return cursor.lastrowid

        except sqlite3.Error as e:
            logger.error(f"Failed to save template: {e}")
            raise

    def get_template(self, template_id: str) -> Optional[Dict]:
        """
        Retrieve job template.

        Args:
            template_id: Template ID

        Returns:
            Template dictionary or None if not found
        """
        try:
            cursor = self._cursor()
            cursor.execute(
                "SELECT * FROM job_templates WHERE id = ?",
                (template_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

        except sqlite3.Error as e:
            logger.error(f"Failed to get template: {e}")
            raise

    def get_all_templates(self) -> List[Dict]:
        """
        Retrieve all job templates.

        Returns:
            List of template dictionaries
        """
        try:
            cursor = self._cursor()
            cursor.execute(
                "SELECT id, name, description, workflow_type, created_at FROM job_templates "
                "ORDER BY created_at DESC"
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Failed to get templates: {e}")
            raise

    def delete_template(self, template_id: str) -> bool:
        """
        Delete job template.

        Args:
            template_id: Template ID

        Returns:
            True if successful
        """
        try:
            cursor = self._cursor()
            cursor.execute(
                "DELETE FROM job_templates WHERE id = ?",
                (template_id,)
            )
            self.connection.commit()
            logger.info(f"Deleted template: {template_id}")
            return True

        except sqlite3.Error as e:
            logger.error(f"Failed to delete template: {e}")
            raise

    # Transfer History Methods

    def save_transfer(self, transfer, connection_id: str):
        """
        Save file transfer record.

        Args:
            transfer: TransferTask object
            connection_id: Connection profile ID
        """
        try:
            cursor = self._cursor()

            cursor.execute("""
                INSERT INTO transfers
                (connection_id, transfer_type, local_path, remote_path, file_size,
                 bytes_transferred, status, started_at, completed_at, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                connection_id,
                getattr(transfer, 'transfer_type', 'unknown'),
                getattr(transfer, 'local_path', ''),
                getattr(transfer, 'remote_path', ''),
                getattr(transfer, 'file_size', 0),
                getattr(transfer, 'bytes_transferred', 0),
                getattr(transfer, 'status', 'pending'),
                getattr(transfer, 'started_at', None),
                getattr(transfer, 'completed_at', None),
                getattr(transfer, 'error_message', '')
            ))

            self.connection.commit()
            logger.debug(f"Saved transfer record")

        except sqlite3.Error as e:
            logger.error(f"Failed to save transfer: {e}")

    def get_transfer_history(self, connection_id: str, limit: int = 50) -> List[Dict]:
        """
        Retrieve file transfer history.

        Args:
            connection_id: Connection profile ID
            limit: Maximum number of transfers to retrieve

        Returns:
            List of transfer dictionaries
        """
        try:
            cursor = self._cursor()
            cursor.execute(
                "SELECT * FROM transfers WHERE connection_id = ? "
                "ORDER BY started_at DESC LIMIT ?",
                (connection_id, limit)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Failed to get transfer history: {e}")
            return []

    # Bookmark Methods

    def save_bookmark(self, connection_id: str, path: str, label: str) -> int:
        """
        Save directory bookmark.

        Args:
            connection_id: Connection profile ID
            path: Remote path to bookmark
            label: Display label

        Returns:
            Bookmark ID
        """
        try:
            cursor = self._cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO bookmarks
                (connection_id, path, label)
                VALUES (?, ?, ?)
            """, (connection_id, path, label))

            self.connection.commit()
            logger.debug(f"Saved bookmark: {path} -> {label}")
            return cursor.lastrowid

        except sqlite3.Error as e:
            logger.error(f"Failed to save bookmark: {e}")
            raise

    def get_bookmarks(self, connection_id: str) -> List[Dict]:
        """
        Retrieve bookmarks for a connection.

        Args:
            connection_id: Connection profile ID

        Returns:
            List of bookmark dictionaries
        """
        try:
            cursor = self._cursor()
            cursor.execute(
                "SELECT * FROM bookmarks WHERE connection_id = ? "
                "ORDER BY label ASC",
                (connection_id,)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Failed to get bookmarks: {e}")
            return []

    def delete_bookmark(self, bookmark_id: str) -> bool:
        """
        Delete bookmark.

        Args:
            bookmark_id: Bookmark ID

        Returns:
            True if successful
        """
        try:
            cursor = self._cursor()
            cursor.execute(
                "DELETE FROM bookmarks WHERE id = ?",
                (bookmark_id,)
            )
            self.connection.commit()
            logger.debug(f"Deleted bookmark: {bookmark_id}")
            return True

        except sqlite3.Error as e:
            logger.error(f"Failed to delete bookmark: {e}")
            raise

    # Notification Methods

    def save_notification(self, ntype: str, message: str, job_id: str = "") -> int:
        """
        Save notification record.

        Args:
            ntype: Notification type (job_completed, job_failed, transfer_done, etc.)
            message: Notification message
            job_id: Optional job ID if related to a job

        Returns:
            Notification ID
        """
        try:
            cursor = self._cursor()

            cursor.execute("""
                INSERT INTO notifications
                (notification_type, message, job_id)
                VALUES (?, ?, ?)
            """, (ntype, message, job_id))

            self.connection.commit()
            logger.debug(f"Saved notification: {ntype}")
            return cursor.lastrowid

        except sqlite3.Error as e:
            logger.error(f"Failed to save notification: {e}")
            raise

    def get_notifications(self, limit: int = 50) -> List[Dict]:
        """
        Retrieve notifications.

        Args:
            limit: Maximum number of notifications to retrieve

        Returns:
            List of notification dictionaries
        """
        try:
            cursor = self._cursor()
            cursor.execute(
                "SELECT * FROM notifications "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Failed to get notifications: {e}")
            return []

    def mark_notification_read(self, notification_id: str) -> bool:
        """
        Mark notification as read.

        Args:
            notification_id: Notification ID

        Returns:
            True if successful
        """
        try:
            cursor = self._cursor()
            cursor.execute(
                "UPDATE notifications SET is_read = 1 WHERE id = ?",
                (notification_id,)
            )
            self.connection.commit()
            logger.debug(f"Marked notification as read: {notification_id}")
            return True

        except sqlite3.Error as e:
            logger.error(f"Failed to mark notification read: {e}")
            raise
