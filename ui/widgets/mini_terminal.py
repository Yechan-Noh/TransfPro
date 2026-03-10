"""
Lightweight embedded terminal widget for the File Transfer tab.

Provides a compact local or remote shell without the toolbars and
quick-command buttons of the full TerminalTab.  Two instances are
placed below the local and remote file browser panes, respectively.

Local terminal  → runs a local subprocess (bash/zsh).
Remote terminal → opens a paramiko SSH channel (requires SSHManager).
"""

import logging
import os
import pty
import re
import select
import shlex
import socket
import struct
import subprocess
import sys
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPlainTextEdit, QHBoxLayout, QLabel,
    QPushButton, QMenu, QInputDialog, QMessageBox,
    QDialog, QFormLayout, QDialogButtonBox, QLineEdit,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QEvent, QSettings, QTimer
from PyQt5.QtGui import (
    QFont, QColor, QTextCursor, QTextCharFormat,
)

logger = logging.getLogger(__name__)

MAX_SCROLLBACK = 5000

# ── Styles ──
_TERM_QSS = """
    QPlainTextEdit {
        background-color: #1e1e1e;
        color: #cccccc;
        border: none;
        padding: 2px 4px;
        selection-background-color: #264f78;
        selection-color: #ffffff;
    }
"""

_HEADER_QSS = """
    QWidget {
        background: #24273a;
        border-top: 1px solid #363a4f;
    }
"""

_LABEL_QSS = "color: #7dc4e4; font-size: 10px; font-weight: bold; padding-left: 6px;"

_QUICK_BTN_QSS = """
    QPushButton {
        background: rgba(14, 165, 233, 0.1);
        color: #7dc4e4;
        border: 1px solid rgba(14, 165, 233, 0.15);
        border-radius: 3px;
        padding: 1px 6px;
        font-size: 11px;
        font-weight: 600;
    }
    QPushButton:hover { background: rgba(14, 165, 233, 0.25); color: #91d7e3; }
    QPushButton:pressed { background: rgba(14, 165, 233, 0.05); }
"""

_ADD_BTN_QSS = """
    QPushButton {
        background: rgba(166, 218, 149, 0.08);
        color: rgba(166, 218, 149, 0.6);
        border: 1px solid rgba(166, 218, 149, 0.12);
        border-radius: 3px;
        padding: 1px 4px;
        font-size: 10px;
        font-weight: bold;
    }
    QPushButton:hover { background: rgba(166, 218, 149, 0.2); color: #a6da95; }
"""


# ── Background reader threads ──

class _RemoteReaderThread(QThread):
    """Read from a paramiko SSH channel in the background.

    Uses blocking ``recv()`` with a short timeout instead of
    polling ``recv_ready()`` + ``sleep()``.
    """
    data_received = pyqtSignal(str)
    closed = pyqtSignal()

    def __init__(self, channel):
        super().__init__()
        self.channel = channel
        self._running = True

    def run(self):
        try:
            self.channel.settimeout(0.05)
            while self._running and self.channel and not self.channel.closed:
                try:
                    data = self.channel.recv(4096)
                    if data:
                        self.data_received.emit(
                            data.decode('utf-8', errors='replace'))
                    else:
                        break
                except socket.timeout:
                    continue
                except (EOFError, OSError):
                    break
                except Exception:
                    break
            if self._running:
                self.closed.emit()
        except Exception as e:
            logger.error(f"Mini-terminal remote reader error: {e}")

    def stop(self):
        self._running = False
        self.wait(200)


class _LocalReaderThread(QThread):
    """Read from a local PTY master fd in the background.

    Uses ``select()`` with a short timeout so the thread can check its
    ``_running`` flag regularly and exit cleanly without relying on
    ``os.close()`` from another thread (which has undefined behaviour
    on Linux and can hang if the fd number was reused).
    """
    data_received = pyqtSignal(str)
    closed = pyqtSignal()

    def __init__(self, master_fd: int):
        super().__init__()
        self.master_fd = master_fd
        self._running = True

    def run(self):
        fd = self.master_fd
        try:
            while self._running:
                try:
                    # Wait up to 100 ms for data; allows checking _running
                    ready, _, _ = select.select([fd], [], [], 0.1)
                    if not ready:
                        continue  # timeout — check _running and loop
                    data = os.read(fd, 4096)
                    if data:
                        self.data_received.emit(
                            data.decode('utf-8', errors='replace'))
                    else:
                        break  # EOF
                except (OSError, ValueError):
                    break  # fd closed or invalid
            if self._running:
                self.closed.emit()
        except Exception as e:
            if self._running:
                logger.error(f"Mini-terminal local reader error: {e}")

    def stop(self):
        self._running = False
        self.wait(500)  # select timeout is 100 ms, so 500 ms is plenty


# ── CSI tokenizer (same regex as TerminalTab) ──
_RE_TOKEN = re.compile(
    r'(\x1b\[([\x20-\x3f]*)([\x40-\x7e]))'   # CSI sequence
    r'|(\x1b\].*?(?:\x07|\x1b\\))'             # OSC sequence
    r'|(\x1b[\(\)][0-9A-B])'                    # Charset select
    r'|(\x1b[=>NOM78Hc])'                       # Other short ESC
)


class MiniTerminal(QWidget):
    """Compact terminal widget — local or remote.

    Parameters
    ----------
    is_remote : bool
        True for an SSH channel terminal, False for a local shell.
    ssh_manager : optional
        Required when *is_remote* is True.
    """

    _DEFAULT_REMOTE_COMMANDS = [
        ("ls -lh", "ls"),
        ("df -h .", "Disk Free"),
        ("pwd", "pwd"),
        ("whoami", "whoami"),
    ]

    _DEFAULT_LOCAL_COMMANDS = [
        ("ls -lh", "ls"),
        ("du -sh *", "Disk Usage"),
        ("pwd", "pwd"),
    ]

    def __init__(self, is_remote: bool = False, ssh_manager=None, parent=None):
        super().__init__(parent)
        self.is_remote = is_remote
        self.ssh_manager = ssh_manager

        # State
        self._connected = False
        self._channel = None       # paramiko channel (remote)
        self._process = None       # subprocess.Popen  (local)
        self._master_fd = -1       # PTY master fd     (local)
        self._reader: Optional[QThread] = None
        self._erase_char = b'\x7f'
        self._last_cd_path: Optional[str] = None  # dedup repeated cd calls

        # Quick commands
        self._quick_commands = self._load_quick_commands()

        # SGR (ANSI colour) state
        self._sgr_fmt = QTextCharFormat()
        self._sgr_default_fg = QColor('#cccccc')
        self._sgr_default_bg = QColor('#1e1e1e')
        self._sgr_fmt.setForeground(self._sgr_default_fg)
        self._sgr_bold = False

        self._setup_ui()

    # ─────────────────────── UI ───────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Thin header bar
        header = QWidget()
        header.setFixedHeight(24)
        header.setStyleSheet(_HEADER_QSS)
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(4, 0, 4, 0)
        hlay.setSpacing(4)

        label_text = "Remote Shell" if self.is_remote else "Local Shell"
        self._header_label = QLabel(label_text)
        self._header_label.setStyleSheet(_LABEL_QSS)
        hlay.addWidget(self._header_label)

        # Separator
        sep = QLabel("|")
        sep.setStyleSheet("color: rgba(202,211,245,0.15); font-size: 10px;")
        hlay.addWidget(sep)

        # Quick command buttons container
        self._quick_btn_layout = QHBoxLayout()
        self._quick_btn_layout.setContentsMargins(0, 0, 0, 0)
        self._quick_btn_layout.setSpacing(3)
        hlay.addLayout(self._quick_btn_layout)
        self._rebuild_quick_buttons()

        hlay.addStretch()

        layout.addWidget(header)

        # Terminal display
        self.display = QPlainTextEdit()
        self.display.setReadOnly(False)
        self.display.setUndoRedoEnabled(False)
        self.display.setFont(self._mono_font(10))
        self.display.setStyleSheet(_TERM_QSS)
        self.display.setFocusPolicy(Qt.StrongFocus)
        self.display.setCursorWidth(2)
        self.display.installEventFilter(self)

        layout.addWidget(self.display)
        self.setLayout(layout)

    @staticmethod
    def _mono_font(size: int) -> QFont:
        for family in ('Menlo', 'Consolas', 'DejaVu Sans Mono', 'Monospace'):
            f = QFont(family, size)
            if f.exactMatch():
                return f
        f = QFont()
        f.setStyleHint(QFont.Monospace)
        f.setPointSize(size)
        return f

    # ─────────────────── Quick commands ───────────────────

    def _settings_key(self) -> str:
        return "MiniTermQuickCmds_remote" if self.is_remote else "MiniTermQuickCmds_local"

    def _load_quick_commands(self) -> list:
        defaults = (self._DEFAULT_REMOTE_COMMANDS if self.is_remote
                    else self._DEFAULT_LOCAL_COMMANDS)
        settings = QSettings("TransfPro", "TransfPro")
        count = settings.beginReadArray(self._settings_key())
        if count == 0:
            settings.endArray()
            return list(defaults)
        cmds = []
        for i in range(count):
            settings.setArrayIndex(i)
            cmd = settings.value("command", "")
            label = settings.value("label", "")
            if cmd and label:
                cmds.append((cmd, label))
        settings.endArray()
        return cmds if cmds else list(defaults)

    def _save_quick_commands(self):
        settings = QSettings("TransfPro", "TransfPro")
        settings.beginWriteArray(self._settings_key(), len(self._quick_commands))
        for i, (cmd, label) in enumerate(self._quick_commands):
            settings.setArrayIndex(i)
            settings.setValue("command", cmd)
            settings.setValue("label", label)
        settings.endArray()
        settings.sync()

    def _rebuild_quick_buttons(self):
        layout = self._quick_btn_layout
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for idx, (cmd, label) in enumerate(self._quick_commands):
            btn = QPushButton(label)
            btn.setToolTip(cmd)
            btn.setFixedHeight(18)
            btn.setStyleSheet(_QUICK_BTN_QSS)
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.clicked.connect(lambda checked, c=cmd: self._send_quick_command(c))
            btn.customContextMenuRequested.connect(
                lambda pos, i=idx, b=btn: self._show_quick_menu(pos, i, b)
            )
            layout.addWidget(btn)

        add_btn = QPushButton("+")
        add_btn.setToolTip("Add quick command")
        add_btn.setFixedHeight(18)
        add_btn.setFixedWidth(22)
        add_btn.setStyleSheet(_ADD_BTN_QSS)
        add_btn.clicked.connect(self._add_quick_command)
        layout.addWidget(add_btn)

    def _send_quick_command(self, command: str):
        if not self._connected:
            return
        lines = command.strip().split('\n')
        if len(lines) == 1:
            self._send_bytes((lines[0] + '\n').encode('utf-8'))
        else:
            for i, line in enumerate(lines):
                if i == 0:
                    self._send_bytes((line + '\n').encode('utf-8'))
                else:
                    QTimer.singleShot(
                        i * 200,
                        lambda ln=line: self._send_bytes((ln + '\n').encode('utf-8'))
                    )
        self.display.setFocus()

    def _show_quick_menu(self, pos, index: int, button: QPushButton):
        menu = QMenu(self)
        edit_action = menu.addAction("Edit")
        remove_action = menu.addAction("Remove")
        action = menu.exec_(button.mapToGlobal(pos))
        if action == edit_action:
            self._edit_quick_command(index)
        elif action == remove_action:
            self._remove_quick_command(index)

    def _quick_cmd_dialog(self, title: str, name: str = "", command: str = ""):
        """Show a dialog to enter/edit a quick command (same as full terminal).

        Returns (name, command) or (None, None) if cancelled.
        """
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setMinimumWidth(480)
        dialog.setMinimumHeight(280)

        layout = QVBoxLayout()

        # Name row
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        name_input = QLineEdit(name)
        name_input.setPlaceholderText("e.g. My Jobs")
        name_layout.addWidget(name_input)
        layout.addLayout(name_layout)

        # Command area (multi-line)
        layout.addWidget(QLabel("Command (one per line for multi-line):"))
        cmd_input = QPlainTextEdit()
        cmd_input.setPlaceholderText(
            "e.g. squeue -u $USER\n\n"
            "For multi-line, each line is sent separately:\n"
            "cd /scratch/$USER\n"
            "ls -la\n"
            "cat slurm-*.out"
        )
        cmd_input.setFont(self._mono_font(11))
        cmd_input.setStyleSheet("""
            QPlainTextEdit {
                background: #1e2030;
                color: #cad3f5;
                border: 1px solid #363a4f;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        cmd_input.setPlainText(command)
        layout.addWidget(cmd_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.setLayout(layout)

        if dialog.exec_() == QDialog.Accepted:
            n = name_input.text().strip()
            c = cmd_input.toPlainText().strip()
            if n and c:
                return n, c
        return None, None

    def _add_quick_command(self):
        name, command = self._quick_cmd_dialog("Add Quick Command")
        if name and command:
            self._quick_commands.append((command, name))
            self._save_quick_commands()
            self._rebuild_quick_buttons()

    def _edit_quick_command(self, index: int):
        cmd, label = self._quick_commands[index]
        new_name, new_cmd = self._quick_cmd_dialog("Edit Quick Command", label, cmd)
        if new_name and new_cmd:
            self._quick_commands[index] = (new_cmd, new_name)
            self._save_quick_commands()
            self._rebuild_quick_buttons()

    def _remove_quick_command(self, index: int):
        cmd, label = self._quick_commands[index]
        reply = QMessageBox.question(
            self, "Remove", f'Remove "{label}"?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._quick_commands.pop(index)
            self._save_quick_commands()
            self._rebuild_quick_buttons()

    # ─────────────────────── Connection ───────────────────────

    def connect_terminal(self):
        """Start the shell session (local or remote)."""
        if self._connected:
            return
        if self.is_remote:
            self._connect_remote()
        else:
            self._connect_local()

    def _connect_remote(self):
        if not self.ssh_manager or not self.ssh_manager.is_connected():
            return
        try:
            transport = self.ssh_manager._client.get_transport()
            if not transport or not transport.is_active():
                return
            self._channel = transport.open_session()
            self._channel.get_pty(term='xterm-256color', width=120, height=24)
            self._channel.invoke_shell()
            self._channel.settimeout(0.1)

            # Start reader immediately — it picks up the MOTD as it arrives.
            self._reader = _RemoteReaderThread(self._channel)
            self._reader.data_received.connect(self._on_data, Qt.QueuedConnection)
            self._reader.closed.connect(self._on_closed, Qt.QueuedConnection)
            self._reader.start()

            self._connected = True
            self._header_label.setText("Remote Shell  ●")
            self._header_label.setStyleSheet(
                _LABEL_QSS.replace('#7dc4e4', '#a6da95'))
            logger.info("Mini-terminal remote connected")
        except Exception as e:
            logger.error(f"Mini-terminal remote connect failed: {e}")

    def _connect_local(self):
        try:
            shell = os.environ.get('SHELL', '/bin/bash')
            # Use a real PTY so the shell produces prompts and handles line editing
            master_fd, slave_fd = pty.openpty()

            # Set initial window size on the PTY
            try:
                import fcntl
                import termios
                winsize = struct.pack('HHHH', 24, 120, 0, 0)
                fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)
            except Exception:
                pass

            env = {**os.environ, 'TERM': 'xterm-256color'}
            self._process = subprocess.Popen(
                [shell, '-i', '-l'],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                preexec_fn=os.setsid,
                env=env,
                close_fds=True,
            )
            os.close(slave_fd)  # parent doesn't need slave end
            self._master_fd = master_fd

            self._reader = _LocalReaderThread(master_fd)
            self._reader.data_received.connect(self._on_data, Qt.QueuedConnection)
            self._reader.closed.connect(self._on_closed, Qt.QueuedConnection)
            self._reader.start()

            self._connected = True
            self._header_label.setText("Local Shell  ●")
            self._header_label.setStyleSheet(
                _LABEL_QSS.replace('#7dc4e4', '#a6da95'))
            logger.info("Mini-terminal local connected")
        except Exception as e:
            logger.error(f"Mini-terminal local connect failed: {e}")

    def disconnect_terminal(self):
        """Tear down the shell session.

        For remote terminals: closes the channel first (unblocks recv),
        then waits for the reader thread.

        For local terminals: signals the reader to stop first (it uses
        select() with a timeout so it can exit on its own), waits for
        it, THEN closes the fd.  This avoids the Linux undefined-
        behaviour of os.close() on an fd that another thread is blocked
        in os.read() on — which can hang if the fd number was reused
        by another subsystem (e.g. Paramiko SSH sockets).
        """
        self._connected = False

        if self.is_remote:
            # ── Remote: close channel first to unblock recv() ──
            if self._channel:
                try:
                    self._channel.close()
                except Exception:
                    pass
                self._channel = None

            # Stop reader after channel is closed
            if self._reader:
                try:
                    self._reader.data_received.disconnect()
                    self._reader.closed.disconnect()
                except (TypeError, RuntimeError):
                    pass
                self._reader.stop()
                self._reader = None

        else:
            # ── Local: kill process → stop reader → close fd ──
            # Killing the process closes the slave end of the PTY,
            # which makes select() on the master fd return readable
            # and os.read() returns b'' (EOF).  This gives the reader
            # a fast clean exit.  We must NOT os.close() the master fd
            # while the reader thread might be in os.read() — on Linux
            # that has undefined behaviour and hangs if the fd number
            # was reused by another subsystem (e.g. Paramiko sockets).

            # 1. Kill the subprocess (unblocks the reader via EOF)
            if self._process:
                try:
                    import signal
                    os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    try:
                        self._process.terminate()
                    except Exception:
                        pass
                try:
                    self._process.wait(timeout=0.3)
                except Exception:
                    pass
                self._process = None

            # 2. Stop the reader thread (should exit almost immediately
            #    now that the process is dead and the PTY sends EOF)
            if self._reader:
                try:
                    self._reader.data_received.disconnect()
                    self._reader.closed.disconnect()
                except (TypeError, RuntimeError):
                    pass
                self._reader.stop()
                self._reader = None

            # 3. Now safe to close the fd — no thread is reading it.
            if self._master_fd >= 0:
                try:
                    os.close(self._master_fd)
                except OSError:
                    pass
                self._master_fd = -1

        label = "Remote Shell" if self.is_remote else "Local Shell"
        self._header_label.setText(label)
        self._header_label.setStyleSheet(_LABEL_QSS)

    def _on_closed(self):
        self._connected = False
        label = "Remote Shell" if self.is_remote else "Local Shell"
        self._header_label.setText(f"{label}  (closed)")

    # ─────────────────── cd helper ───────────────────

    def cd(self, path: str):
        """Send a cd command to the shell (skips if already at that path)."""
        if not self._connected:
            return
        if path == self._last_cd_path:
            return
        self._last_cd_path = path
        cmd = f"cd {shlex.quote(path)}\n"
        self._send_bytes(cmd.encode('utf-8'))

    # ─────────────────── Key input ───────────────────

    _SPECIAL_KEYMAP = {
        Qt.Key_Return:    b'\r',
        Qt.Key_Enter:     b'\r',
        Qt.Key_Tab:       b'\t',
        Qt.Key_Escape:    b'\x1b',
        Qt.Key_Up:        b'\x1b[A',
        Qt.Key_Down:      b'\x1b[B',
        Qt.Key_Right:     b'\x1b[C',
        Qt.Key_Left:      b'\x1b[D',
        Qt.Key_Home:      b'\x1b[H',
        Qt.Key_End:       b'\x1b[F',
        Qt.Key_Delete:    b'\x1b[3~',
        Qt.Key_PageUp:    b'\x1b[5~',
        Qt.Key_PageDown:  b'\x1b[6~',
        Qt.Key_Insert:    b'\x1b[2~',
    }

    def eventFilter(self, obj, event):
        if obj is self.display and event.type() == QEvent.KeyPress:
            key = event.key()
            mods = event.modifiers()
            text = event.text()

            # Cmd+C / Ctrl+Shift+C → copy
            if key == Qt.Key_C:
                if (mods & Qt.ControlModifier and not mods & Qt.ShiftModifier
                        and not mods & Qt.MetaModifier):
                    if self.display.textCursor().hasSelection():
                        self.display.copy()
                        return True
                    # else fall through to send Ctrl+C
                if mods & Qt.MetaModifier and mods & Qt.ShiftModifier:
                    self.display.copy()
                    return True

            # Cmd+V / Ctrl+Shift+V → paste
            if key == Qt.Key_V:
                if (mods & Qt.ControlModifier and not mods & Qt.ShiftModifier
                        and not mods & Qt.MetaModifier):
                    self._paste()
                    return True
                if mods & Qt.MetaModifier and mods & Qt.ShiftModifier:
                    self._paste()
                    return True

            # Cmd+A → select all
            if key == Qt.Key_A:
                if mods & Qt.ControlModifier and not mods & Qt.MetaModifier:
                    self.display.selectAll()
                    return True

            # Send to shell
            if self._connected:
                self._send_key(event)
                return True

            return True  # consume when not connected too
        return super().eventFilter(obj, event)

    def _paste(self):
        from PyQt5.QtWidgets import QApplication
        cb = QApplication.clipboard()
        text = cb.text()
        if text and self._connected:
            self._send_bytes(text.encode('utf-8'))

    def _send_key(self, event):
        try:
            key = event.key()
            text = event.text()
            mods = event.modifiers()

            if key in (Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt,
                       Qt.Key_Meta, Qt.Key_CapsLock, Qt.Key_NumLock):
                return

            data = None

            if key == Qt.Key_Backspace:
                data = self._erase_char
            elif key in self._SPECIAL_KEYMAP:
                data = self._SPECIAL_KEYMAP[key]
            else:
                is_ctrl = (bool(mods & Qt.MetaModifier) if sys.platform == 'darwin'
                           else bool(mods & Qt.ControlModifier))
                if is_ctrl and not (mods & Qt.AltModifier):
                    if key == Qt.Key_C:
                        data = b'\x03'
                    elif key == Qt.Key_D:
                        data = b'\x04'
                    elif key == Qt.Key_L:
                        data = b'\x0c'
                    elif key == Qt.Key_Z:
                        data = b'\x1a'
                    elif Qt.Key_A <= key <= Qt.Key_Z:
                        data = bytes([key - Qt.Key_A + 1])

                if data is None and text and key != Qt.Key_Backspace:
                    data = text.encode('utf-8')

            if data:
                self._send_bytes(data)
        except Exception as e:
            logger.error(f"Mini-terminal send key error: {e}")
            if 'closed' in str(e).lower():
                self._connected = False

    def _send_bytes(self, data: bytes):
        try:
            if self.is_remote and self._channel:
                self._channel.sendall(data)
            elif not self.is_remote and self._master_fd >= 0:
                os.write(self._master_fd, data)
        except Exception as e:
            logger.error(f"Mini-terminal send error: {e}")

    # ─────────────── Data reception / VT100 ───────────────

    # ANSI colour palettes (same as TerminalTab)
    _ANSI_COLORS = [
        QColor('#2e3436'), QColor('#cc0000'), QColor('#4e9a06'), QColor('#c4a000'),
        QColor('#3465a4'), QColor('#75507b'), QColor('#06989a'), QColor('#d3d7cf'),
    ]
    _ANSI_BRIGHT = [
        QColor('#555753'), QColor('#ef2929'), QColor('#8ae234'), QColor('#fce94f'),
        QColor('#729fcf'), QColor('#ad7fa8'), QColor('#34e2e2'), QColor('#eeeeec'),
    ]

    def _on_data(self, data: str):
        """Parse incoming VT100 data and render in the display."""
        try:
            cursor = self.display.textCursor()
            cursor.movePosition(QTextCursor.End)

            data = data.replace('\r\n', '\n')

            pos = 0
            buf = []

            def _flush():
                if not buf:
                    return
                text = ''.join(buf)
                buf.clear()
                remaining = (cursor.block().length() - 1 - cursor.positionInBlock())
                if remaining > 0:
                    n = min(len(text), remaining)
                    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, n)
                cursor.insertText(text, self._sgr_fmt)

            for m in _RE_TOKEN.finditer(data):
                seg = data[pos:m.start()]
                if seg:
                    for ch in seg:
                        self._handle_char(ch, cursor, buf, _flush)
                pos = m.end()
                _flush()
                if m.group(1):
                    self._handle_csi(m.group(2), m.group(3), cursor)

            tail = data[pos:]
            if tail:
                for ch in tail:
                    self._handle_char(ch, cursor, buf, _flush)
            _flush()

            self.display.setTextCursor(cursor)
            self.display.ensureCursorVisible()

            # Trim scrollback
            doc = self.display.document()
            if doc.blockCount() > MAX_SCROLLBACK:
                excess = doc.blockCount() - MAX_SCROLLBACK
                tc = QTextCursor(doc)
                tc.movePosition(QTextCursor.Start)
                for _ in range(excess):
                    tc.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor)
                tc.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
                tc.removeSelectedText()
                tc.deleteChar()

        except Exception as e:
            logger.error(f"Mini-terminal data error: {e}")

    @staticmethod
    def _handle_char(ch, cursor, buf, flush_fn):
        if ch == '\x08':
            flush_fn()
            if cursor.positionInBlock() > 0:
                cursor.movePosition(QTextCursor.Left)
        elif ch == '\r':
            flush_fn()
            cursor.movePosition(QTextCursor.StartOfBlock)
        elif ch == '\n':
            flush_fn()
            if cursor.atEnd():
                cursor.insertText('\n')
            else:
                cursor.movePosition(QTextCursor.Down)
                cursor.movePosition(QTextCursor.StartOfBlock)
        elif ch == '\x07':
            pass
        elif ch >= ' ' or ch == '\t':
            buf.append(ch)

    def _handle_csi(self, params_str, final, cursor):
        params = []
        if params_str:
            for p in params_str.split(';'):
                p = p.strip()
                if p.isdigit():
                    params.append(int(p))
                elif p == '':
                    params.append(0)
                else:
                    return
        n = params[0] if params else None

        if final == 'm':
            self._handle_sgr(params or [0])
        elif final == 'A':
            cursor.movePosition(QTextCursor.Up, QTextCursor.MoveAnchor, max(n or 1, 1))
        elif final == 'B':
            cursor.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor, max(n or 1, 1))
        elif final == 'C':
            cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, max(n or 1, 1))
        elif final == 'D':
            cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, max(n or 1, 1))
        elif final == 'G':
            col = max((n or 1) - 1, 0)
            cursor.movePosition(QTextCursor.StartOfBlock)
            line_len = cursor.block().length() - 1
            if col > 0:
                cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, min(col, line_len))
        elif final in ('H', 'f'):  # Cursor Position  \x1b[row;colH
            # Clamp to sane limits to prevent memory exhaustion
            row = min(max((params[0] if len(params) > 0 else 1), 1), 500)
            col = min(max((params[1] if len(params) > 1 else 1), 1), 500)
            doc = cursor.document()
            while doc.blockCount() < row:
                cursor.movePosition(QTextCursor.End)
                cursor.insertText('\n')
            block = doc.findBlockByNumber(row - 1)
            cursor.setPosition(block.position())
            line_len = block.length() - 1
            if col - 1 > line_len:
                cursor.movePosition(QTextCursor.EndOfBlock)
                cursor.insertText(' ' * (col - 1 - line_len))
            else:
                cursor.movePosition(
                    QTextCursor.Right, QTextCursor.MoveAnchor, col - 1)
        elif final == 'K':
            mode = n or 0
            if mode == 0:
                cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                cursor.removeSelectedText()
            elif mode == 1:
                cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
                cursor.removeSelectedText()
            elif mode == 2:
                cursor.movePosition(QTextCursor.StartOfBlock)
                cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                cursor.removeSelectedText()
        elif final == 'J':
            mode = n or 0
            if mode == 0:
                cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
                cursor.removeSelectedText()
            elif mode == 1:
                cursor.movePosition(QTextCursor.Start, QTextCursor.KeepAnchor)
                cursor.removeSelectedText()
            elif mode == 2:
                cursor.select(QTextCursor.Document)
                cursor.removeSelectedText()
        elif final == 'P':
            cnt = max(n or 1, 1)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, cnt)
            cursor.removeSelectedText()

    # ── SGR (ANSI colour) ──

    def _handle_sgr(self, params):
        i = 0
        while i < len(params):
            p = params[i]
            if p == 0:
                self._sgr_fmt = QTextCharFormat()
                self._sgr_fmt.setForeground(self._sgr_default_fg)
                self._sgr_bold = False
            elif p == 1:
                self._sgr_bold = True
                self._sgr_fmt.setFontWeight(QFont.Bold)
            elif p == 22:
                self._sgr_bold = False
                self._sgr_fmt.setFontWeight(QFont.Normal)
            elif p == 7:
                fg = self._sgr_fmt.foreground().color()
                bg = self._sgr_fmt.background().color()
                self._sgr_fmt.setForeground(bg if bg.isValid() else self._sgr_default_bg)
                self._sgr_fmt.setBackground(fg if fg.isValid() else self._sgr_default_fg)
            elif 30 <= p <= 37:
                c = self._ANSI_BRIGHT[p - 30] if self._sgr_bold else self._ANSI_COLORS[p - 30]
                self._sgr_fmt.setForeground(c)
            elif p == 39:
                self._sgr_fmt.setForeground(self._sgr_default_fg)
            elif 40 <= p <= 47:
                self._sgr_fmt.setBackground(self._ANSI_COLORS[p - 40])
            elif p == 49:
                self._sgr_fmt.clearBackground()
            elif 90 <= p <= 97:
                self._sgr_fmt.setForeground(self._ANSI_BRIGHT[p - 90])
            elif 100 <= p <= 107:
                self._sgr_fmt.setBackground(self._ANSI_BRIGHT[p - 100])
            elif p == 38 and i + 1 < len(params):
                if params[i + 1] == 5 and i + 2 < len(params):
                    self._sgr_fmt.setForeground(self._color_256(params[i + 2]))
                    i += 2
                elif params[i + 1] == 2 and i + 4 < len(params):
                    self._sgr_fmt.setForeground(QColor(params[i+2], params[i+3], params[i+4]))
                    i += 4
            elif p == 48 and i + 1 < len(params):
                if params[i + 1] == 5 and i + 2 < len(params):
                    self._sgr_fmt.setBackground(self._color_256(params[i + 2]))
                    i += 2
                elif params[i + 1] == 2 and i + 4 < len(params):
                    self._sgr_fmt.setBackground(QColor(params[i+2], params[i+3], params[i+4]))
                    i += 4
            i += 1

    def _color_256(self, idx: int) -> QColor:
        if idx < 8:
            return self._ANSI_COLORS[idx]
        if idx < 16:
            return self._ANSI_BRIGHT[idx - 8]
        if idx < 232:
            idx -= 16
            r = (idx // 36) * 51
            g = ((idx // 6) % 6) * 51
            b = (idx % 6) * 51
            return QColor(r, g, b)
        grey = 8 + (idx - 232) * 10
        return QColor(grey, grey, grey)

    # ─────────────────── Cleanup ───────────────────

    def closeEvent(self, event):
        if getattr(self, '_shutdown_done', False):
            super().closeEvent(event)
            return
        self.disconnect_terminal()
        super().closeEvent(event)
