"""SSH connection manager with 2FA support."""

import logging
import threading
import time
from pathlib import Path
from typing import Optional, Callable, Tuple, List
import paramiko
from paramiko import SSHClient, Transport, SFTPClient
from paramiko.ssh_exception import (
    SSHException,
    AuthenticationException,
    NoValidConnectionsError
)

from transfpro.models.connection import ConnectionProfile
from transfpro.config.constants import SFTP_WINDOW_SIZE, SFTP_MAX_PACKET_SIZE

logger = logging.getLogger(__name__)


class _TransfProHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    """Host key policy that prompts for user approval via callback."""

    def __init__(self, on_unknown_host=None):
        self._on_unknown_host = on_unknown_host

    def missing_host_key(self, client, hostname, key):
        fingerprint = key.get_fingerprint().hex(':')
        key_type = key.get_name()
        logger.debug(f"Unknown host key for {hostname}: {key_type} {fingerprint}")

        if self._on_unknown_host:
            approved = self._on_unknown_host(hostname, key_type, fingerprint)
            if not approved:
                raise SSHException(
                    f"Host key for {hostname} rejected by user"
                )

        # Save to known_hosts
        known_hosts = Path.home() / ".transfpro" / "known_hosts"
        known_hosts.parent.mkdir(parents=True, exist_ok=True)
        client.get_host_keys().add(hostname, key.get_name(), key)
        try:
            client.save_host_keys(str(known_hosts))
        except OSError as e:
            logger.warning(f"Could not save known_hosts: {e}")


class SSHManager:
    """Thread-safe SSH connection manager with 2FA support."""

    def __init__(self):
        """Initialize SSH manager."""
        self._lock = threading.RLock()
        self._client: Optional[SSHClient] = None
        self._transport: Optional[Transport] = None
        self._sftp: Optional[SFTPClient] = None
        self._profile: Optional[ConnectionProfile] = None
        self._password: Optional[str] = None
        self._is_connected = False
        self._shutdown = False
        self._keepalive_timer: Optional[threading.Timer] = None
        self._2fa_response_sent = False

        # Known hosts file
        self._known_hosts_path = Path.home() / ".transfpro" / "known_hosts"

        # Callbacks
        self.on_connected: Optional[Callable] = None
        self.on_disconnected: Optional[Callable] = None
        self.on_2fa_waiting: Optional[Callable] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_unknown_host_key: Optional[Callable] = None

    def connect(self, profile: ConnectionProfile, password: str) -> bool:
        """
        Connect to cluster with automatic 2FA handling.

        Args:
            profile: Connection profile with server details
            password: SSH password

        Returns:
            True if connection successful, False otherwise
        """
        with self._lock:
            try:
                if self._is_connected:
                    logger.warning("Already connected, disconnecting first")
                    self.disconnect()

                self._profile = profile
                self._password = password
                self._shutdown = False
                self._2fa_response_sent = False

                logger.debug(f"Connecting to server (port {profile.port})")

                import socket

                if profile.has_2fa:
                    # ── 2FA flow (e.g. NCSA Delta with Duo) ──
                    # Sequence: auth_password (partial) → auth_interactive (Duo)
                    # Retry up to 3 times — Delta's load balancer can
                    # occasionally reject the first connection attempt.

                    import time
                    max_attempts = 3
                    last_error = None

                    for attempt in range(1, max_attempts + 1):
                        try:
                            logger.debug(f"2FA connection attempt {attempt}/{max_attempts}")

                            # Clean up any previous failed transport
                            if self._transport:
                                try:
                                    self._transport.close()
                                except Exception:
                                    pass
                                self._transport = None

                            # Step 1: Open raw TCP socket + SSH transport
                            sock = socket.create_connection(
                                (profile.host, profile.port),
                                timeout=profile.timeout or 30
                            )
                            self._sock = sock  # Store reference for cleanup on failure
                            self._transport = Transport(sock)
                            self._transport.use_compression(True)
                            self._transport.start_client()

                            # Step 2: Password auth (partial auth expected for 2FA)
                            logger.debug("Sending credentials...")
                            try:
                                self._transport.auth_password(
                                    username=profile.username,
                                    password=password,
                                )
                            except AuthenticationException as e:
                                if self._transport.is_authenticated():
                                    logger.debug("Partial auth succeeded")
                                else:
                                    logger.debug("Partial auth (expected for 2FA)")

                            # Step 3: If not yet authenticated, keyboard-interactive for Duo
                            if not self._transport.is_authenticated():
                                logger.debug("Starting 2FA (keyboard-interactive)...")
                                if self.on_2fa_waiting:
                                    self.on_2fa_waiting()

                                self._transport.auth_interactive(
                                    username=profile.username,
                                    handler=self._2fa_handler,
                                )
                            else:
                                logger.debug("Authenticated without 2FA")

                            # If we got here without exception, break out of retry loop
                            last_error = None
                            break

                        except AuthenticationException as e:
                            last_error = e
                            logger.warning(f"Attempt {attempt} failed: {e}")
                            if attempt < max_attempts:
                                logger.info(f"Retrying in {attempt} second(s)...")
                                time.sleep(attempt)  # increasing backoff

                    if last_error:
                        logger.error(f"All {max_attempts} attempts failed: {last_error}")
                        if self.on_error:
                            self.on_error(f"2FA authentication failed: {last_error}")
                        return False

                    if not self._transport.is_authenticated():
                        raise AuthenticationException("Authentication failed after 2FA")

                    logger.debug("Authentication successful")

                    # Wrap transport in SSHClient for exec_command / open_sftp
                    self._client = SSHClient()
                    self._load_host_keys(self._client)
                    self._client.set_missing_host_key_policy(
                        _TransfProHostKeyPolicy(self.on_unknown_host_key)
                    )
                    self._client._transport = self._transport

                else:
                    # ── Standard password/key flow ──
                    self._client = SSHClient()
                    self._load_host_keys(self._client)
                    self._client.set_missing_host_key_policy(
                        _TransfProHostKeyPolicy(self.on_unknown_host_key)
                    )

                    connect_kwargs = dict(
                        hostname=profile.host,
                        port=profile.port,
                        username=profile.username,
                        timeout=profile.timeout or 30,
                        look_for_keys=False,
                        allow_agent=False,
                        compress=True,
                    )

                    if profile.auth_method == "key" and profile.key_path:
                        connect_kwargs['key_filename'] = profile.key_path
                    else:
                        connect_kwargs['password'] = password

                    self._client.connect(**connect_kwargs)

                    if not self._client.get_transport() or not self._client.get_transport().is_authenticated():
                        raise AuthenticationException("Authentication failed")

                self._is_connected = True
                # Clear password from memory after successful auth
                self._password = None
                self._start_keepalive()

                logger.info("SSH connection established")
                if self.on_connected:
                    self.on_connected()

                return True

            except (SSHException, AuthenticationException, NoValidConnectionsError, OSError) as e:
                logger.error(f"SSH connection failed: {e}")
                if self.on_error:
                    self.on_error(f"Connection failed: {str(e)}")
                self.disconnect()
                return False

    def _2fa_handler(
        self,
        title: str,
        instructions: str,
        prompt_list: List[Tuple[str, bool]]
    ) -> List[str]:
        """
        Interactive authentication handler for 2FA.

        Called by paramiko during auth_interactive. Detects password vs 2FA
        prompts and responds appropriately.

        Args:
            title: Authentication title
            instructions: Instructions text
            prompt_list: List of (prompt_text, echo_bool) tuples

        Returns:
            List of responses matching prompt_list
        """
        logger.debug(f"2FA handler called with {len(prompt_list)} prompt(s)")

        responses = []
        password_sent = False

        for prompt_text, echo in prompt_list:
            prompt_lower = prompt_text.strip().lower()

            # Detect password prompt
            if any(kw in prompt_lower for kw in ["password", "passwd"]):
                logger.debug("  -> password prompt detected")
                responses.append(self._password)
                password_sent = True

            # Detect 2FA / Duo prompts
            elif any(kw in prompt_lower for kw in
                    ["duo", "push", "factor", "passcode", "code", "accept",
                     "choice", "option", "press", "enter a", "1."]):
                two_fa = self._profile.two_fa_response or "1"
                logger.debug("  -> 2FA prompt detected")
                responses.append(two_fa)
                self._2fa_response_sent = True

            # Unknown prompt — after password was already sent via auth_password,
            # the Duo step may show a generic prompt. Default to 2FA response.
            else:
                two_fa = self._profile.two_fa_response or "1"
                if password_sent:
                    logger.debug("  -> unknown prompt after password, sending 2FA")
                else:
                    logger.debug("  -> unknown first prompt, sending 2FA")
                responses.append(two_fa)
                self._2fa_response_sent = True

        return responses

    def disconnect(self):
        """Close all connections and cleanup."""
        with self._lock:
            logger.debug("Disconnecting SSH")
            self._shutdown = True

            # Stop keepalive FIRST to prevent timer firing during teardown
            timer = self._keepalive_timer
            self._keepalive_timer = None
            if timer:
                timer.cancel()

            # Set a short socket timeout before closing to prevent blocking
            # on dead/stale connections (TCP FIN handshake can hang for minutes)
            try:
                transport = self._transport or (
                    self._client.get_transport() if self._client else None
                )
                if transport:
                    sock = transport.sock
                    if sock:
                        sock.settimeout(2)
            except Exception:
                pass

            # Close SFTP
            if self._sftp:
                try:
                    self._sftp.close()
                except Exception as e:
                    logger.debug(f"Error closing SFTP: {e}")
                self._sftp = None

            # Close transport
            if self._transport:
                try:
                    self._transport.close()
                except Exception as e:
                    logger.debug(f"Error closing transport: {e}")
                self._transport = None

            # Close client
            if self._client:
                try:
                    self._client.close()
                except Exception as e:
                    logger.debug(f"Error closing client: {e}")
                self._client = None

            # Close raw socket if still open (prevents socket leak on failed connects)
            if hasattr(self, '_sock') and self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None

            was_connected = self._is_connected
            self._is_connected = False
            self._password = None  # Clear password from memory

            if was_connected and self.on_disconnected:
                self.on_disconnected()

            logger.debug("Disconnected")

    def is_connected(self) -> bool:
        """
        Check if currently connected.

        Also verifies transport is still active.

        Returns:
            True if connected and transport is active
        """
        with self._lock:
            if not self._is_connected or not self._client:
                return False

            try:
                transport = self._client.get_transport()
                if not transport or not transport.is_active():
                    logger.warning("Transport is not active, marking as disconnected")
                    self._is_connected = False
                    return False
                return True
            except Exception as e:
                logger.debug(f"Error checking connection: {e}")
                return False

    def execute_command(
        self,
        command: str,
        timeout: int = 30
    ) -> Tuple[str, str, int]:
        """
        Execute remote command.

        Args:
            command: Command to execute
            timeout: Command timeout in seconds

        Returns:
            Tuple of (stdout, stderr, exit_code)

        Raises:
            SSHException if not connected or execution fails
        """
        # Only hold the lock long enough to grab the client reference and
        # dispatch exec_command.  The blocking stdout/stderr reads happen
        # OUTSIDE the lock so that keepalive, SFTP, and other threads are
        # not starved.
        with self._lock:
            if not self.is_connected():
                raise SSHException("Not connected")
            client = self._client

        try:
            logger.debug(f"Executing command: {command}")
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)

            # Read output — potentially slow, done outside lock
            stdout_data = stdout.read().decode('utf-8', errors='replace')
            stderr_data = stderr.read().decode('utf-8', errors='replace')
            exit_code = stdout.channel.recv_exit_status()

            logger.debug(f"Command completed with exit code {exit_code}")
            return stdout_data, stderr_data, exit_code

        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            # On timeout or socket errors, mark connection as dead
            if isinstance(e, (TimeoutError, OSError, IOError)):
                logger.warning("Connection appears dead, marking disconnected")
                with self._lock:
                    self._is_connected = False
            raise SSHException(f"Command execution failed: {e}")

    def get_sftp(self) -> SFTPClient:
        """
        Get or create SFTP client with tuned window/packet sizes.

        Returns:
            SFTP client instance

        Raises:
            SSHException if not connected
        """
        with self._lock:
            if not self.is_connected():
                raise SSHException("Not connected")

            if self._sftp is None:
                try:
                    transport = self._client.get_transport()
                    if not transport:
                        raise SSHException("No active transport")

                    chan = transport.open_session(
                        window_size=SFTP_WINDOW_SIZE,
                        max_packet_size=SFTP_MAX_PACKET_SIZE,
                    )
                    chan.invoke_subsystem("sftp")
                    self._sftp = SFTPClient(chan)

                    logger.debug("Created SFTP client with tuned window/packet sizes")
                except Exception as e:
                    logger.error(f"Failed to create SFTP client: {e}")
                    raise SSHException(f"Failed to create SFTP client: {e}")

            return self._sftp

    def open_sftp(self) -> SFTPClient:
        """
        Open a NEW, dedicated SFTP session with tuned window/packet sizes.

        Uses larger window (2 MB) and packet sizes (64 KB) than Paramiko
        defaults for significantly higher throughput over high-latency links.
        The caller is responsible for closing the returned client.

        Returns:
            A new SFTPClient instance

        Raises:
            SSHException if not connected
        """
        with self._lock:
            if not self.is_connected():
                raise SSHException("Not connected")
            try:
                transport = self._client.get_transport()
                if not transport:
                    raise SSHException("No active transport")

                # Open channel with larger window/packet for better throughput
                chan = transport.open_session(
                    window_size=SFTP_WINDOW_SIZE,
                    max_packet_size=SFTP_MAX_PACKET_SIZE,
                )
                chan.invoke_subsystem("sftp")
                sftp = SFTPClient(chan)

                logger.debug(
                    f"Opened SFTP session (window={SFTP_WINDOW_SIZE}, "
                    f"max_packet={SFTP_MAX_PACKET_SIZE})"
                )
                return sftp
            except Exception as e:
                logger.error(f"Failed to open SFTP session: {e}")
                raise SSHException(f"Failed to open SFTP session: {e}")

    def _load_host_keys(self, client: SSHClient):
        """Load known host keys from the TransfPro known_hosts file."""
        try:
            if self._known_hosts_path.exists():
                client.load_host_keys(str(self._known_hosts_path))
                logger.debug("Loaded known host keys")
        except Exception as e:
            logger.debug(f"Could not load known_hosts: {e}")

    def _start_keepalive(self):
        """Start sending keepalive packets."""
        if not self._profile:
            return

        # Capture interval as a local so the timer closure never touches
        # self._profile (which may be None by the time the timer fires).
        interval = getattr(self._profile, 'keepalive_interval', 30)

        def send_keepalive():
            """Send keepalive packet."""
            try:
                with self._lock:
                    if self._shutdown or not self._is_connected or not self._transport:
                        return
                    self._transport.send_ignore()
                    logger.debug("Keepalive packet sent")

                    # Check shutdown again before rescheduling
                    if self._shutdown:
                        return
                    # Schedule next keepalive (still inside lock to
                    # prevent race with disconnect cancelling the timer)
                    self._keepalive_timer = threading.Timer(
                        interval, send_keepalive
                    )
                    self._keepalive_timer.daemon = True
                    self._keepalive_timer.start()
            except Exception as e:
                logger.warning(f"Keepalive failed — connection lost: {e}")
                # Server-side disconnect detected: mark as disconnected
                # and notify the UI via callback
                with self._lock:
                    was_connected = self._is_connected
                    self._is_connected = False
                    self._keepalive_timer = None
                if was_connected and self.on_disconnected:
                    try:
                        self.on_disconnected()
                    except Exception as cb_err:
                        logger.debug(f"on_disconnected callback error: {cb_err}")

        # Initial keepalive timer
        self._keepalive_timer = threading.Timer(interval, send_keepalive)
        self._keepalive_timer.daemon = True
        self._keepalive_timer.start()
        logger.debug(f"Keepalive started (interval: {interval}s)")

    def reconnect(self, password: Optional[str] = None) -> bool:
        """
        Attempt to reconnect using stored profile.

        Args:
            password: SSH password (required since passwords are not stored)

        Returns:
            True if reconnection successful
        """
        if not self._profile:
            logger.error("No profile stored for reconnection")
            return False
        if not password:
            logger.error("Password required for reconnection")
            return False

        return self.connect(self._profile, password)
