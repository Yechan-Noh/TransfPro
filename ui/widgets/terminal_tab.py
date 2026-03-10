"""
Dual-pane Terminal Tab for TransfPro.

Each side is driven by the corresponding File Transfer pane's connection.
When the File Transfer pane connects to Local or a cluster, MainWindow
signals this tab to open a terminal session using the same SSH transport
(new channel) or a local PTY.  When disconnected, the terminal is cleared
and a waiting placeholder is shown.

Features: VT100 / ANSI-colour handling, search, customisable
quick-command buttons, and font-size controls.
"""

import logging
import os
import pty
import re
import select
import signal as _signal
import socket
import struct
import subprocess
import sys
import time as _time
from typing import Optional, List

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton,
    QLabel, QSizePolicy, QLineEdit, QSplitter, QStackedWidget,
    QApplication, QMenu, QInputDialog, QDialog, QMessageBox,
    QFormLayout, QDialogButtonBox,
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QSize, QSettings, QTimer, QEvent
from PyQt5.QtGui import (
    QFont, QColor, QTextCursor, QTextCharFormat, QTextDocument,
)

from transfpro.core.database import Database

logger = logging.getLogger(__name__)

MAX_SCROLLBACK_LINES = 10000

# ── Styles ──────────────────────────────────────────────────────────

_TOOLBAR_QSS = """
    QWidget {
        background: #1e2030;
        border-bottom: 1px solid rgba(73, 77, 100, 0.3);
    }
"""

_BTN_QSS = """
    QPushButton {
        background: rgba(138, 173, 244, 0.08);
        color: #8aadf4;
        border: 1px solid rgba(138, 173, 244, 0.2);
        border-radius: 4px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: 600;
    }
    QPushButton:hover { background: rgba(138, 173, 244, 0.18); }
    QPushButton:pressed { background: rgba(138, 173, 244, 0.06); }
"""

_DISCONNECT_BTN_QSS = """
    QPushButton {
        background: rgba(237, 135, 150, 0.08);
        color: #ed8796;
        border: 1px solid rgba(237, 135, 150, 0.2);
        border-radius: 4px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: 600;
    }
    QPushButton:hover { background: rgba(237, 135, 150, 0.18); }
    QPushButton:pressed { background: rgba(237, 135, 150, 0.06); }
"""

_QUICK_BTN_QSS = """
    QPushButton {
        background: rgba(14, 165, 233, 0.1);
        color: #7dc4e4;
        border: 1px solid rgba(14, 165, 233, 0.2);
        border-radius: 3px;
        padding: 2px 8px;
        font-size: 11px;
        font-weight: 600;
    }
    QPushButton:hover { background: rgba(14, 165, 233, 0.2); color: #91d7e3; }
    QPushButton:pressed { background: rgba(14, 165, 233, 0.05); }
"""

_TERM_QSS = """
    QPlainTextEdit {
        background-color: #1e1e1e;
        color: #cccccc;
        border: none;
        padding: 5px;
        selection-background-color: #264f78;
        selection-color: #ffffff;
    }
"""

_SEARCH_BAR_QSS = "background-color: #2a2a2e;"

_PLACEHOLDER_QSS = """
    QWidget#placeholder {
        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:1,
            stop:0 #1e2030, stop:1 #181926
        );
    }
"""

# ── Reader threads ──────────────────────────────────────────────────

class _RemoteReaderThread(QThread):
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
                        self.data_received.emit(data.decode('utf-8', errors='replace'))
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
            logger.error(f"Terminal remote reader error: {e}")

    def stop(self):
        self._running = False
        self.wait(300)


class _LocalReaderThread(QThread):
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
                    ready, _, _ = select.select([fd], [], [], 0.1)
                    if not ready:
                        continue
                    data = os.read(fd, 4096)
                    if data:
                        self.data_received.emit(data.decode('utf-8', errors='replace'))
                    else:
                        break
                except (OSError, ValueError):
                    break
            if self._running:
                self.closed.emit()
        except Exception as e:
            if self._running:
                logger.error(f"Terminal local reader error: {e}")

    def stop(self):
        self._running = False
        self.wait(500)


# ── TerminalPane ────────────────────────────────────────────────────

class TerminalPane(QWidget):
    """A single terminal pane: waiting placeholder (page 0) + full terminal (page 1).

    Connections are driven externally by MainWindow (which syncs from
    the File Transfer tab).  No ConnectionSelector is embedded here.
    """

    _DEFAULT_REMOTE_COMMANDS = [
        ("ls -lh", "ls"),
        ("squeue -u $USER", "My Jobs"),
        ("df -h .", "Disk Free"),
        ("pwd", "pwd"),
        ("whoami", "whoami"),
        ("top -bn1 | head -20", "Top Procs"),
    ]

    _DEFAULT_LOCAL_COMMANDS = [
        ("ls -lh", "ls"),
        ("du -sh *", "Disk Usage"),
        ("pwd", "pwd"),
    ]

    # ANSI color palettes
    _ANSI_COLORS = [
        QColor('#2e3436'), QColor('#cc0000'), QColor('#4e9a06'), QColor('#c4a000'),
        QColor('#3465a4'), QColor('#75507b'), QColor('#06989a'), QColor('#d3d7cf'),
    ]
    _ANSI_BRIGHT = [
        QColor('#555753'), QColor('#ef2929'), QColor('#8ae234'), QColor('#fce94f'),
        QColor('#729fcf'), QColor('#ad7fa8'), QColor('#34e2e2'), QColor('#eeeeec'),
    ]

    _RE_TOKEN = re.compile(
        r'(\x1b\[([\x20-\x3f]*)([\x40-\x7e]))'
        r'|(\x1b\][^\x07]{0,256}(?:\x07|\x1b\\))'
        r'|(\x1b[()][\x20-\x7e])'
        r'|(\x1b[^[\]()])'
    )

    def __init__(self, side: str, parent=None):
        super().__init__(parent)
        self._side = side  # "left" or "right"

        # Connection state
        self.is_remote = False
        self.ssh_manager = None
        self.connected_profile = None

        # Terminal state
        self._connected = False
        self._channel = None
        self._process = None
        self._master_fd = -1
        self._reader: Optional[QThread] = None
        self._erase_char = b'\x7f'
        self._base_font_size = 11
        self._search_visible = False

        # Quick commands
        self._quick_commands = self._load_quick_commands()

        # SGR state
        self._sgr_fmt = QTextCharFormat()
        self._sgr_default_fg = QColor('#cccccc')
        self._sgr_default_bg = QColor('#1e1e1e')
        self._sgr_fmt.setForeground(self._sgr_default_fg)
        self._sgr_bold = False

        self._setup_ui()

    # ── UI ──

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()

        # Page 0: Waiting placeholder (no ConnectionSelector)
        placeholder = self._create_placeholder()
        self._stack.addWidget(placeholder)

        # Page 1: Terminal view
        self._terminal_page = QWidget()
        term_layout = QVBoxLayout(self._terminal_page)
        term_layout.setContentsMargins(0, 0, 0, 0)
        term_layout.setSpacing(0)

        # Toolbar
        toolbar = self._create_toolbar()
        term_layout.addWidget(toolbar)

        # Quick commands bar
        self._quick_bar = self._create_quick_bar()
        term_layout.addWidget(self._quick_bar)

        # Search bar (hidden by default)
        self._search_bar = self._create_search_bar()
        self._search_bar.hide()
        term_layout.addWidget(self._search_bar)

        # Terminal display
        self.display = QPlainTextEdit()
        self.display.setReadOnly(False)
        self.display.setUndoRedoEnabled(False)
        self.display.setFont(self._mono_font(self._base_font_size))
        self.display.setCursorWidth(2)
        self.display.setStyleSheet(_TERM_QSS)
        self.display.setFocusPolicy(Qt.StrongFocus)
        self.display.setContextMenuPolicy(Qt.CustomContextMenu)
        self.display.customContextMenuRequested.connect(self._show_context_menu)
        self.display.installEventFilter(self)
        term_layout.addWidget(self.display)

        self._stack.addWidget(self._terminal_page)

        layout.addWidget(self._stack)
        self.setLayout(layout)

    def _create_placeholder(self) -> QWidget:
        """Create a styled waiting page that tells the user to connect via File Transfer."""
        page = QWidget()
        page.setObjectName("placeholder")
        page.setStyleSheet(_PLACEHOLDER_QSS)

        lay = QVBoxLayout(page)
        lay.setAlignment(Qt.AlignCenter)

        icon_lbl = QLabel("⌨")
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 48px; color: #494d64; margin-bottom: 6px;")
        lay.addWidget(icon_lbl)

        side_name = "Left" if self._side == "left" else "Right"
        title_lbl = QLabel(f"{side_name} Terminal")
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet(
            "color: #cad3f5; font-size: 16px; font-weight: 700;"
            " letter-spacing: 0.5px; margin-bottom: 4px;"
        )
        lay.addWidget(title_lbl)

        self._placeholder_hint = QLabel(
            "Connect to a server or local shell\n"
            "in the File Transfer tab to open a terminal here."
        )
        self._placeholder_hint.setAlignment(Qt.AlignCenter)
        self._placeholder_hint.setStyleSheet(
            "color: #6e738d; font-size: 12px; line-height: 1.5;"
        )
        self._placeholder_hint.setWordWrap(True)
        lay.addWidget(self._placeholder_hint)

        return page

    def _create_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(_TOOLBAR_QSS)
        bar.setFixedHeight(30)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(4)

        # Clear
        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet(_BTN_QSS)
        clear_btn.setMaximumHeight(24)
        clear_btn.clicked.connect(lambda: self.display.clear())
        lay.addWidget(clear_btn)

        # Find
        find_btn = QPushButton("Find")
        find_btn.setStyleSheet(_BTN_QSS)
        find_btn.setMaximumHeight(24)
        find_btn.clicked.connect(self._toggle_search)
        lay.addWidget(find_btn)

        # Font size
        font_down = QPushButton("A-")
        font_down.setStyleSheet(_BTN_QSS)
        font_down.setMaximumHeight(24)
        font_down.setFixedWidth(28)
        font_down.clicked.connect(self._font_decrease)
        lay.addWidget(font_down)

        font_up = QPushButton("A+")
        font_up.setStyleSheet(_BTN_QSS)
        font_up.setMaximumHeight(24)
        font_up.setFixedWidth(28)
        font_up.clicked.connect(self._font_increase)
        lay.addWidget(font_up)

        lay.addStretch()

        # Status
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(
            "color: #a6da95; font-weight: bold; font-size: 11px; padding-right: 6px;"
        )
        lay.addWidget(self._status_label)

        return bar

    def _create_quick_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(26)
        bar.setStyleSheet("background: #181926; border-bottom: 1px solid rgba(73,77,100,0.2);")
        self._quick_bar_layout = QHBoxLayout(bar)
        self._quick_bar_layout.setContentsMargins(6, 1, 6, 1)
        self._quick_bar_layout.setSpacing(3)
        self._rebuild_quick_buttons()
        return bar

    def _rebuild_quick_buttons(self):
        lay = self._quick_bar_layout
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        label = QLabel("Quick:")
        label.setStyleSheet("color: #6e738d; font-size: 10px; font-weight: 600;")
        lay.addWidget(label)

        for idx, (cmd, btn_label) in enumerate(self._quick_commands):
            btn = QPushButton(btn_label)
            btn.setToolTip(cmd + "\n\nRight-click to edit or remove")
            btn.setMaximumHeight(20)
            btn.setStyleSheet(_QUICK_BTN_QSS)
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.clicked.connect(lambda checked, c=cmd: self._send_quick_command(c))
            btn.customContextMenuRequested.connect(
                lambda pos, i=idx, b=btn: self._show_quick_menu(pos, i, b))
            lay.addWidget(btn)

        add_btn = QPushButton("+")
        add_btn.setToolTip("Add quick command")
        add_btn.setMaximumHeight(20)
        add_btn.setFixedWidth(24)
        add_btn.setStyleSheet(_QUICK_BTN_QSS)
        add_btn.clicked.connect(self._add_quick_command)
        lay.addWidget(add_btn)

        lay.addStretch()

    def _create_search_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(_SEARCH_BAR_QSS)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(8, 3, 8, 3)
        lay.setSpacing(6)

        lay.addWidget(QLabel("Find:"))

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search...")
        self._search_input.setMaximumWidth(250)
        self._search_input.returnPressed.connect(self._search_next)
        lay.addWidget(self._search_input)

        prev_btn = QPushButton("Prev")
        prev_btn.setMaximumHeight(22)
        prev_btn.setStyleSheet(_BTN_QSS)
        prev_btn.clicked.connect(self._search_prev)
        lay.addWidget(prev_btn)

        next_btn = QPushButton("Next")
        next_btn.setMaximumHeight(22)
        next_btn.setStyleSheet(_BTN_QSS)
        next_btn.clicked.connect(self._search_next)
        lay.addWidget(next_btn)

        self._search_status = QLabel("")
        lay.addWidget(self._search_status)

        lay.addStretch()

        close_btn = QPushButton("X")
        close_btn.setMaximumWidth(22)
        close_btn.setMaximumHeight(22)
        close_btn.setStyleSheet(_BTN_QSS)
        close_btn.clicked.connect(self._close_search)
        lay.addWidget(close_btn)

        return bar

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

    # ── External sync API (called by MainWindow) ──

    def sync_connect(self, is_remote: bool, ssh_manager, profile):
        """Called by MainWindow when the corresponding File Transfer pane connects.

        Opens a terminal session: local PTY or a new SSH channel on the
        same transport that the File Transfer pane uses.

        Args:
            is_remote: True for cluster, False for local
            ssh_manager: The SSHManager from the File Transfer pane (None for local)
            profile: The ConnectionProfile (None for local)
        """
        if getattr(self, '_shutdown_done', False):
            return

        # If already connected, disconnect first
        if self._connected:
            self._disconnect_terminal()
            self.display.clear()

        self.is_remote = is_remote
        self.ssh_manager = ssh_manager
        self.connected_profile = profile

        # Update UI
        if is_remote and profile:
            self._status_label.setText(profile.name)
            self._status_label.setStyleSheet(
                "color: #a6da95; font-weight: bold; font-size: 11px; padding-right: 6px;")
        else:
            self._status_label.setText("Local")
            self._status_label.setStyleSheet(
                "color: #8aadf4; font-weight: bold; font-size: 11px; padding-right: 6px;")

        self._quick_commands = self._load_quick_commands()
        self._rebuild_quick_buttons()
        self._stack.setCurrentIndex(1)
        self._connect_terminal()

    def sync_disconnect(self):
        """Called by MainWindow when the corresponding File Transfer pane disconnects."""
        if getattr(self, '_shutdown_done', False):
            return

        self._disconnect_terminal()
        self.display.clear()
        self.is_remote = False
        self.ssh_manager = None
        self.connected_profile = None
        self._status_label.setText("")
        self._stack.setCurrentIndex(0)

    # ── Terminal connect / disconnect ──

    def _connect_terminal(self):
        if self._connected:
            self._disconnect_terminal()
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
            self._channel.get_pty(term='xterm-256color', width=120, height=40)
            self._channel.invoke_shell()
            self._channel.settimeout(0.1)

            self._reader = _RemoteReaderThread(self._channel)
            self._reader.data_received.connect(self._on_data_received, Qt.QueuedConnection)
            self._reader.closed.connect(self._on_closed, Qt.QueuedConnection)
            self._reader.start()

            self._connected = True
            self.display.setFocus()

            # Auto-detect erase char
            try:
                stdout, _, ec = self.ssh_manager.execute_command(
                    'stty -a 2>/dev/null | head -3', timeout=5)
                if ec == 0 and stdout:
                    m = re.search(r'erase\s*=\s*(\S+)', stdout)
                    if m and m.group(1) == '^H':
                        self._erase_char = b'\x08'
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Terminal remote connect failed: {e}")

    def _connect_local(self):
        try:
            shell = os.environ.get('SHELL', '/bin/bash')
            master_fd, slave_fd = pty.openpty()

            try:
                import fcntl
                import termios
                winsize = struct.pack('HHHH', 40, 120, 0, 0)
                fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)
            except Exception:
                pass

            env = {**os.environ, 'TERM': 'xterm-256color'}
            self._process = subprocess.Popen(
                [shell, '-i', '-l'],
                stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
                preexec_fn=os.setsid, env=env, close_fds=True,
            )
            os.close(slave_fd)
            self._master_fd = master_fd

            self._reader = _LocalReaderThread(master_fd)
            self._reader.data_received.connect(self._on_data_received, Qt.QueuedConnection)
            self._reader.closed.connect(self._on_closed, Qt.QueuedConnection)
            self._reader.start()

            self._connected = True
            self.display.setFocus()
        except Exception as e:
            logger.error(f"Terminal local connect failed: {e}")

    def _disconnect_terminal(self):
        self._connected = False
        if self.is_remote:
            if self._channel:
                try:
                    self._channel.close()
                except Exception:
                    pass
                self._channel = None
            if self._reader:
                try:
                    self._reader.data_received.disconnect()
                    self._reader.closed.disconnect()
                except (TypeError, RuntimeError):
                    pass
                self._reader.stop()
                self._reader = None
        else:
            # Local: kill process → stop reader → close fd
            if self._process:
                try:
                    os.killpg(os.getpgid(self._process.pid), _signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
                try:
                    self._process.wait(timeout=0.3)
                except Exception:
                    pass
                self._process = None

            if self._reader:
                try:
                    self._reader.data_received.disconnect()
                    self._reader.closed.disconnect()
                except (TypeError, RuntimeError):
                    pass
                self._reader.stop()
                self._reader = None

            if self._master_fd >= 0:
                try:
                    os.close(self._master_fd)
                except OSError:
                    pass
                self._master_fd = -1

    def _on_closed(self):
        """Reader thread reports channel/fd closed."""
        if not self._connected:
            return
        self._connected = False
        # Auto-reconnect for remote if SSH still alive
        if self.is_remote and self.ssh_manager and self.ssh_manager.is_connected():
            self._status_label.setText("Reconnecting...")
            QTimer.singleShot(500, self._connect_terminal)

    # ── Data reception & VT100 ──

    def _on_data_received(self, data: str):
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
                block_remaining = cursor.block().length() - 1 - cursor.positionInBlock()
                if block_remaining > 0:
                    n = min(len(text), block_remaining)
                    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, n)
                cursor.insertText(text, self._sgr_fmt)

            for m in self._RE_TOKEN.finditer(data):
                segment = data[pos:m.start()]
                if segment:
                    for ch in segment:
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

            doc = self.display.document()
            if doc.blockCount() > MAX_SCROLLBACK_LINES:
                excess = doc.blockCount() - MAX_SCROLLBACK_LINES
                tc = QTextCursor(doc)
                # Select from start up to end of the excess-th line in one jump
                tc.movePosition(QTextCursor.Start)
                target_block = doc.findBlockByNumber(excess)
                tc.setPosition(target_block.position(), QTextCursor.KeepAnchor)
                tc.removeSelectedText()

        except Exception as e:
            logger.error(f"Error processing terminal data: {e}")

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
        elif final in ('H', 'f'):
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
                cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, col - 1)
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
            count = max(n or 1, 1)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, count)
            cursor.removeSelectedText()
        elif final == '@':
            count = max(n or 1, 1)
            cursor.insertText(' ' * count)
            cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, count)

    def _handle_sgr(self, params):
        fmt = self._sgr_fmt
        i = 0
        while i < len(params):
            code = params[i]
            if code == 0:
                fmt.setForeground(self._sgr_default_fg)
                fmt.setBackground(QColor(0, 0, 0, 0))
                fmt.setFontWeight(QFont.Normal)
                fmt.setFontItalic(False)
                fmt.setFontUnderline(False)
                self._sgr_bold = False
            elif code == 1:
                fmt.setFontWeight(QFont.Bold)
                self._sgr_bold = True
            elif code == 2:
                fmt.setFontWeight(QFont.Light)
                self._sgr_bold = False
            elif code == 3:
                fmt.setFontItalic(True)
            elif code == 4:
                fmt.setFontUnderline(True)
            elif code == 7:
                fg = fmt.foreground().color()
                bg = fmt.background().color()
                if bg.alpha() == 0:
                    bg = self._sgr_default_bg
                fmt.setForeground(bg)
                fmt.setBackground(fg)
            elif code == 22:
                fmt.setFontWeight(QFont.Normal)
                self._sgr_bold = False
            elif code == 23:
                fmt.setFontItalic(False)
            elif code == 24:
                fmt.setFontUnderline(False)
            elif 30 <= code <= 37:
                idx = code - 30
                color = self._ANSI_BRIGHT[idx] if self._sgr_bold else self._ANSI_COLORS[idx]
                fmt.setForeground(color)
            elif code == 38:
                color, skip = self._parse_extended_color(params, i)
                if color:
                    fmt.setForeground(color)
                i += skip
            elif code == 39:
                fmt.setForeground(self._sgr_default_fg)
            elif 40 <= code <= 47:
                fmt.setBackground(self._ANSI_COLORS[code - 40])
            elif code == 48:
                color, skip = self._parse_extended_color(params, i)
                if color:
                    fmt.setBackground(color)
                i += skip
            elif code == 49:
                fmt.setBackground(QColor(0, 0, 0, 0))
            elif 90 <= code <= 97:
                fmt.setForeground(self._ANSI_BRIGHT[code - 90])
            elif 100 <= code <= 107:
                fmt.setBackground(self._ANSI_BRIGHT[code - 100])
            i += 1

    @classmethod
    def _parse_extended_color(cls, params, i):
        if i + 1 >= len(params):
            return None, 0
        mode = params[i + 1]
        if mode == 5 and i + 2 < len(params):
            return cls._color_from_256(params[i + 2]), 2
        if mode == 2 and i + 4 < len(params):
            r = max(0, min(255, params[i + 2]))
            g = max(0, min(255, params[i + 3]))
            b = max(0, min(255, params[i + 4]))
            return QColor(r, g, b), 4
        return None, 0

    @classmethod
    def _color_from_256(cls, n):
        if n < 0 or n > 255:
            return QColor('#cccccc')
        if n < 8:
            return cls._ANSI_COLORS[n]
        if n < 16:
            return cls._ANSI_BRIGHT[n - 8]
        if n < 232:
            n -= 16
            b = (n % 6) * 51
            n //= 6
            g = (n % 6) * 51
            r = (n // 6) * 51
            return QColor(r, g, b)
        gray = 8 + (n - 232) * 10
        return QColor(gray, gray, gray)

    # ── Key event handling ──

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
            modifiers = event.modifiers()
            key = event.key()

            # Cmd+C / Ctrl+Shift+C → copy
            if key == Qt.Key_C:
                if (modifiers & Qt.ControlModifier
                        and not (modifiers & Qt.ShiftModifier)
                        and not (modifiers & Qt.MetaModifier)):
                    self._copy_selection()
                    return True
                if modifiers & Qt.MetaModifier and modifiers & Qt.ShiftModifier:
                    self._copy_selection()
                    return True

            # Cmd+V / Ctrl+Shift+V → paste
            if key == Qt.Key_V:
                if (modifiers & Qt.ControlModifier
                        and not (modifiers & Qt.ShiftModifier)
                        and not (modifiers & Qt.MetaModifier)):
                    self._paste_clipboard()
                    return True
                if modifiers & Qt.MetaModifier and modifiers & Qt.ShiftModifier:
                    self._paste_clipboard()
                    return True

            # Cmd+A / Ctrl+A → select all
            if key == Qt.Key_A:
                if (modifiers & Qt.ControlModifier
                        and not (modifiers & Qt.ShiftModifier)
                        and not (modifiers & Qt.MetaModifier)):
                    self.display.selectAll()
                    return True

            # Cmd+F / Ctrl+F → search
            if key == Qt.Key_F:
                if modifiers & (Qt.ControlModifier | Qt.MetaModifier):
                    self._toggle_search()
                    return True

            # Escape → close search
            if key == Qt.Key_Escape and self._search_visible:
                self._close_search()
                return True

            # Send to terminal
            if self._connected:
                self._send_key(event)
                return True
            return True

        return super().eventFilter(obj, event)

    def _send_key(self, event):
        try:
            key = event.key()
            text = event.text()
            modifiers = event.modifiers()

            if key in (Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta,
                       Qt.Key_CapsLock, Qt.Key_NumLock):
                return

            data = None

            if key == Qt.Key_Backspace:
                data = self._erase_char
            elif key in self._SPECIAL_KEYMAP:
                data = self._SPECIAL_KEYMAP[key]
            else:
                if sys.platform == 'darwin':
                    is_ctrl = bool(modifiers & Qt.MetaModifier)
                else:
                    is_ctrl = bool(modifiers & Qt.ControlModifier)

                if is_ctrl and not (modifiers & Qt.AltModifier):
                    ctrl_map = {
                        Qt.Key_C: b'\x03', Qt.Key_D: b'\x04', Qt.Key_L: b'\x0c',
                        Qt.Key_Z: b'\x1a', Qt.Key_A: b'\x01', Qt.Key_E: b'\x05',
                        Qt.Key_K: b'\x0b', Qt.Key_U: b'\x15', Qt.Key_W: b'\x17',
                        Qt.Key_R: b'\x12',
                    }
                    data = ctrl_map.get(key)
                    if data is None and Qt.Key_A <= key <= Qt.Key_Z:
                        data = bytes([key - Qt.Key_A + 1])

                if data is None and text and key != Qt.Key_Backspace:
                    data = text.encode('utf-8')

            if data:
                self._send_bytes(data)
        except Exception as e:
            logger.error(f"Error sending key: {e}")

    def _send_bytes(self, data: bytes):
        if not self._connected:
            return
        try:
            if self.is_remote and self._channel:
                self._channel.sendall(data)
            elif not self.is_remote and self._master_fd >= 0:
                os.write(self._master_fd, data)
        except (OSError, EOFError):
            pass  # Channel/fd closed during disconnect — ignore
        except Exception as e:
            logger.error(f"Terminal send error: {e}")

    # ── Quick commands ──

    def _send_quick_command(self, command: str):
        if not self._connected:
            return
        try:
            lines = command.split('\n')
            if len(lines) <= 1:
                self._send_bytes((command + '\n').encode('utf-8'))
            else:
                for i, line in enumerate(lines):
                    line = line.rstrip()
                    if not line:
                        continue
                    if i == 0:
                        self._send_bytes((line + '\n').encode('utf-8'))
                    else:
                        QTimer.singleShot(
                            i * 100,
                            lambda l=line: self._send_bytes((l + '\n').encode('utf-8'))
                        )
            self.display.setFocus()
        except Exception as e:
            logger.error(f"Error sending quick command: {e}")

    def _show_quick_menu(self, pos, index, button):
        menu = QMenu(self)
        edit_action = menu.addAction("Edit")
        remove_action = menu.addAction("Remove")
        action = menu.exec_(button.mapToGlobal(pos))
        if action == edit_action:
            self._edit_quick_command(index)
        elif action == remove_action:
            self._remove_quick_command(index)

    def _add_quick_command(self):
        name, command = self._quick_cmd_dialog("Add Quick Command", "", "")
        if name and command:
            self._quick_commands.append((command, name))
            self._save_quick_commands()
            self._rebuild_quick_buttons()

    def _edit_quick_command(self, index):
        cmd, label = self._quick_commands[index]
        new_name, new_cmd = self._quick_cmd_dialog("Edit Quick Command", label, cmd)
        if new_name and new_cmd:
            self._quick_commands[index] = (new_cmd, new_name)
            self._save_quick_commands()
            self._rebuild_quick_buttons()

    def _remove_quick_command(self, index):
        cmd, label = self._quick_commands[index]
        reply = QMessageBox.question(
            self, "Remove Quick Command", f'Remove "{label}"?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self._quick_commands.pop(index)
            self._save_quick_commands()
            self._rebuild_quick_buttons()

    def _quick_cmd_dialog(self, title, name, command):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setMinimumWidth(420)
        dialog.setMinimumHeight(240)

        layout = QVBoxLayout()

        name_lay = QHBoxLayout()
        name_lay.addWidget(QLabel("Name:"))
        name_input = QLineEdit(name)
        name_input.setPlaceholderText("e.g. My Jobs")
        name_lay.addWidget(name_input)
        layout.addLayout(name_lay)

        layout.addWidget(QLabel("Command:"))
        from PyQt5.QtWidgets import QPlainTextEdit as _PTE
        cmd_input = _PTE()
        cmd_input.setPlaceholderText("e.g. squeue -u $USER")
        cmd_input.setFont(self._mono_font(11))
        cmd_input.setStyleSheet("""
            QPlainTextEdit {
                background: #1e2030; color: #cad3f5;
                border: 1px solid #363a4f; border-radius: 4px; padding: 6px;
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

    def _qsettings_key(self):
        kind = "remote" if self.is_remote else "local"
        return f"TermPaneQuickCmds_{self._side}_{kind}"

    def _load_quick_commands(self):
        settings = QSettings("TransfPro", "TransfPro")
        key = self._qsettings_key()
        count = settings.beginReadArray(key)
        if count == 0:
            settings.endArray()
            return list(self._DEFAULT_REMOTE_COMMANDS if self.is_remote
                        else self._DEFAULT_LOCAL_COMMANDS)
        commands = []
        for i in range(count):
            settings.setArrayIndex(i)
            cmd = settings.value("command", "")
            label = settings.value("label", "")
            if cmd and label:
                commands.append((cmd, label))
        settings.endArray()
        return commands if commands else list(
            self._DEFAULT_REMOTE_COMMANDS if self.is_remote
            else self._DEFAULT_LOCAL_COMMANDS)

    def _save_quick_commands(self):
        settings = QSettings("TransfPro", "TransfPro")
        key = self._qsettings_key()
        settings.beginWriteArray(key, len(self._quick_commands))
        for i, (cmd, label) in enumerate(self._quick_commands):
            settings.setArrayIndex(i)
            settings.setValue("command", cmd)
            settings.setValue("label", label)
        settings.endArray()
        settings.sync()

    # ── Search ──

    def _toggle_search(self):
        self._search_visible = not self._search_visible
        self._search_bar.setVisible(self._search_visible)
        if self._search_visible:
            self._search_input.setFocus()
            self._search_input.selectAll()
        else:
            self._clear_search_highlights()
            self.display.setFocus()

    def _close_search(self):
        self._search_visible = False
        self._search_bar.hide()
        self._clear_search_highlights()
        self.display.setFocus()

    def _search_next(self):
        text = self._search_input.text()
        if not text:
            return
        found = self.display.find(text)
        if not found:
            cursor = self.display.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.display.setTextCursor(cursor)
            found = self.display.find(text)
        self._search_status.setText("" if found else "Not found")

    def _search_prev(self):
        text = self._search_input.text()
        if not text:
            return
        found = self.display.find(text, QTextDocument.FindBackward)
        if not found:
            cursor = self.display.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.display.setTextCursor(cursor)
            found = self.display.find(text, QTextDocument.FindBackward)
        self._search_status.setText("" if found else "Not found")

    def _clear_search_highlights(self):
        cursor = self.display.textCursor()
        cursor.clearSelection()
        self.display.setTextCursor(cursor)
        self._search_status.setText("")

    # ── Copy / Paste / Context menu ──

    def _copy_selection(self):
        cursor = self.display.textCursor()
        if cursor.hasSelection():
            QApplication.clipboard().setText(cursor.selectedText())

    def _paste_clipboard(self):
        if not self._connected:
            return
        text = QApplication.clipboard().text()
        if text:
            self._send_bytes(text.encode('utf-8'))

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction("Copy", self._copy_selection, "Ctrl+Shift+C")
        menu.addAction("Paste", self._paste_clipboard, "Ctrl+Shift+V")
        menu.addAction("Select All", self.display.selectAll)
        menu.addSeparator()
        menu.addAction("Clear Screen", lambda: self.display.clear())
        menu.exec_(self.display.mapToGlobal(pos))

    # ── Font size ──

    def _font_increase(self):
        self._base_font_size = min(self._base_font_size + 1, 24)
        self.display.setFont(self._mono_font(self._base_font_size))

    def _font_decrease(self):
        self._base_font_size = max(self._base_font_size - 1, 7)
        self.display.setFont(self._mono_font(self._base_font_size))

    # ── Cleanup ──

    def cleanup(self):
        self._disconnect_terminal()


# ── TerminalTab (dual-pane container) ───────────────────────────────

class TerminalTab(QWidget):
    """Dual-pane terminal tab — connections are synced from File Transfer."""

    connection_lost = pyqtSignal()

    def __init__(self, database: Database, parent=None):
        super().__init__(parent)
        self.database = database

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)

        self.left_pane = TerminalPane("left", parent=self)
        self.right_pane = TerminalPane("right", parent=self)

        splitter.addWidget(self.left_pane)
        splitter.addWidget(self.right_pane)
        splitter.setSizes([500, 500])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        layout.addWidget(splitter)
        self.setLayout(layout)

    # ── Sync API (called by MainWindow) ──

    def sync_connect(self, side: str, is_remote: bool, ssh_manager, profile):
        """Connect the left or right terminal pane."""
        pane = self.left_pane if side == "left" else self.right_pane
        pane.sync_connect(is_remote, ssh_manager, profile)

    def sync_disconnect(self, side: str):
        """Disconnect the left or right terminal pane."""
        pane = self.left_pane if side == "left" else self.right_pane
        pane.sync_disconnect()

    # ── Legacy compatibility ──

    def connect_terminal(self):
        """No-op — connections are driven by File Transfer sync."""
        pass

    def disconnect_terminal(self):
        """Disconnect both panes."""
        self.left_pane._disconnect_terminal()
        self.right_pane._disconnect_terminal()

    def cleanup(self):
        self.left_pane.cleanup()
        self.right_pane.cleanup()
