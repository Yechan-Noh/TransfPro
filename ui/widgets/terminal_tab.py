"""
Embedded SSH Terminal Emulator for TransfPro.

This module provides an interactive SSH terminal embedded in the main window,
featuring basic VT100 escape code handling, quick SLURM commands, search,
and real-time output streaming from remote SSH channels.
"""

import logging
import socket
import time
import re
from typing import Optional, List
from collections import deque
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton,
    QToolBar, QLabel, QMessageBox, QSizePolicy, QLineEdit,
    QApplication, QMenu, QInputDialog, QDialog,
    QFormLayout, QDialogButtonBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QSize, QSettings, QTimer
from PyQt5.QtGui import (
    QFont, QColor, QTextCursor, QTextCharFormat, QTextDocument
)
import paramiko

logger = logging.getLogger(__name__)

# Maximum number of document blocks (lines) before old lines are trimmed
MAX_SCROLLBACK_LINES = 10000

# ── Compact button styles (override global theme) ──
_TERM_BTN_STYLE = """
    QPushButton {
        background: #24273a;
        color: #cad3f5;
        border: 1px solid #363a4f;
        border-radius: 4px;
        padding: 3px 10px;
        font-size: 12px;
        font-weight: 600;
    }
    QPushButton:hover { background: #363a4f; }
    QPushButton:pressed { background: #1a1b26; }
"""














_QUICK_BTN_STYLE = """
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

_SEND_BTN_STYLE = """
    QPushButton {
        background: rgba(166, 218, 149, 0.1);
        color: #a6da95;
        border: 1px solid rgba(166, 218, 149, 0.2);
        border-radius: 3px;
        padding: 2px 10px;
        font-size: 11px;
        font-weight: 600;
    }
    QPushButton:hover { background: rgba(166, 218, 149, 0.2); }
    QPushButton:pressed { background: rgba(166, 218, 149, 0.05); }
"""


class TerminalReaderThread(QThread):
    """Background thread that reads data from SSH channel."""

    data_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    channel_closed = pyqtSignal()

    def __init__(self, channel: paramiko.Channel):
        super().__init__()
        self.channel = channel
        self._running = True

    def run(self):
        """Read from channel in background loop."""
        try:
            while self._running and self.channel and not self.channel.closed:
                try:
                    if self.channel.recv_ready():
                        data = self.channel.recv(4096)
                        if data:
                            decoded = data.decode('utf-8', errors='replace')
                            self.data_received.emit(decoded)
                        else:
                            break
                    else:
                        time.sleep(0.02)
                except socket.timeout:
                    continue
                except EOFError:
                    break
                except OSError:
                    # Channel/transport was closed — expected during disconnect
                    break
                except Exception:
                    # Catch-all for paramiko internal errors during shutdown
                    break

            if not self._running:
                return
            self.channel_closed.emit()

        except Exception as e:
            if self._running:
                logger.error(f"Terminal reader thread error: {e}")

    def stop(self):
        self._running = False
        # Close channel to unblock any pending recv_ready() / sleep loop
        if self.channel and not self.channel.closed:
            try:
                self.channel.close()
            except Exception:
                pass
        self.wait(timeout=3000)


class TerminalTab(QWidget):
    """
    Embedded SSH terminal emulator using paramiko channel.

    Features:
    - Real-time SSH output streaming
    - Keyboard input capture and transmission
    - Basic VT100 escape code handling
    - Quick command buttons (customizable)
    - Search in terminal output (Ctrl+F)
    - Copy selected text (Ctrl+Shift+C)
    - Font size adjustment
    - Reconnect button
    - Scrollback buffer limit
    """

    connection_lost = pyqtSignal()

    # Default quick commands (used on first launch)
    _DEFAULT_QUICK_COMMANDS = [
        ("ls -lh", "List Files"),
        ("df -h .", "Disk Free"),
        ("pwd", "pwd"),
        ("whoami", "whoami"),
        ("uname -a", "System Info"),
        ("top -bn1 | head -20", "Top Processes"),
    ]

    def __init__(self, ssh_manager, parent=None):
        super().__init__(parent)
        self.ssh_manager = ssh_manager
        self.channel: Optional[paramiko.Channel] = None
        self.reader_thread: Optional[TerminalReaderThread] = None

        # Quick commands (mutable, persisted via QSettings)
        self._quick_commands: List[tuple] = self._load_quick_commands()

        # Terminal state
        self._connected = False
        self._base_font_size = 11
        self._search_visible = False
        self._erase_char = b'\x7f'  # default ^? (DEL); auto-detected on connect

        # SGR (Select Graphic Rendition) state for ANSI color support
        self._sgr_fmt = QTextCharFormat()  # current text format
        self._sgr_default_fg = QColor('#cccccc')
        self._sgr_default_bg = QColor('#1e1e1e')
        self._sgr_fmt.setForeground(self._sgr_default_fg)
        self._sgr_bold = False

        # Setup UI
        self._setup_ui()

        # Connect to SSH manager signals if available
        if hasattr(ssh_manager, 'connection_status_changed'):
            ssh_manager.connection_status_changed.connect(self._on_connection_status_changed)

    def _setup_ui(self):
        """Setup user interface components."""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Main toolbar
        toolbar = self._create_toolbar()
        main_layout.addWidget(toolbar)

        # Quick commands bar
        quick_bar = self._create_quick_commands_bar()
        main_layout.addWidget(quick_bar)

        # Search bar (hidden by default)
        self.search_bar = self._create_search_bar()
        self.search_bar.setVisible(False)
        main_layout.addWidget(self.search_bar)

        # Terminal display — NOT read-only so the blinking cursor is visible;
        # all keyboard input is intercepted by eventFilter and sent to the
        # SSH channel instead of being inserted into the document.
        self.terminal_display = QPlainTextEdit()
        self.terminal_display.setReadOnly(False)
        self.terminal_display.setFont(self._get_monospace_font(self._base_font_size))
        self.terminal_display.setCursorWidth(2)
        self.terminal_display.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #cccccc;
                border: none;
                margin: 0px;
                padding: 5px;
                selection-background-color: #264f78;
                selection-color: #ffffff;
            }
        """)
        self.terminal_display.setFocusPolicy(Qt.StrongFocus)
        self.terminal_display.setContextMenuPolicy(Qt.CustomContextMenu)
        self.terminal_display.customContextMenuRequested.connect(self._show_context_menu)
        # Disable undo/redo to prevent Cmd+Z from corrupting terminal state
        self.terminal_display.setUndoRedoEnabled(False)

        # Event filter for key interception
        self.terminal_display.installEventFilter(self)

        main_layout.addWidget(self.terminal_display)
        self.setLayout(main_layout)

    def _create_toolbar(self) -> QToolBar:
        """Create main toolbar."""
        toolbar = QToolBar("Terminal Controls")
        toolbar.setIconSize(QSize(16, 16))

        # Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.setToolTip("Clear terminal screen")
        clear_btn.setStyleSheet(_TERM_BTN_STYLE)
        clear_btn.clicked.connect(self._on_clear_terminal)
        toolbar.addWidget(clear_btn)

        # Search button
        search_btn = QPushButton("Find")
        search_btn.setToolTip("Search in terminal output (Ctrl+F)")
        search_btn.setStyleSheet(_TERM_BTN_STYLE)
        search_btn.clicked.connect(self._toggle_search)
        toolbar.addWidget(search_btn)

        # Reconnect button
        self.reconnect_btn = QPushButton("Reconnect")
        self.reconnect_btn.setToolTip("Reconnect the terminal session")
        self.reconnect_btn.setStyleSheet(_TERM_BTN_STYLE)
        self.reconnect_btn.clicked.connect(self._on_reconnect)
        toolbar.addWidget(self.reconnect_btn)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        # Status label
        self.status_label = QLabel("Not connected")
        self.status_label.setStyleSheet(
            "color: #ff6b6b; font-weight: bold; font-size: 12px; "
            "padding-right: 12px; margin-right: 8px;"
        )
        toolbar.addWidget(self.status_label)

        return toolbar

    def _create_quick_commands_bar(self) -> QWidget:
        """Create the quick-commands bar with interactive buttons."""
        self._quick_bar = QWidget()
        self._quick_bar_layout = QHBoxLayout()
        self._quick_bar_layout.setContentsMargins(4, 2, 4, 2)
        self._quick_bar_layout.setSpacing(4)
        self._quick_bar.setLayout(self._quick_bar_layout)
        self._rebuild_quick_buttons()
        return self._quick_bar

    def _rebuild_quick_buttons(self):
        """Rebuild all quick-command buttons from current list."""
        layout = self._quick_bar_layout
        # Remove all existing widgets
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        label = QLabel("Quick:")
        layout.addWidget(label)

        for idx, (cmd, btn_label) in enumerate(self._quick_commands):
            btn = QPushButton(btn_label)
            lines = cmd.split('\n')
            if len(lines) > 1:
                tip = '\n'.join(lines) + f'\n\n({len(lines)} lines) — Right-click to edit or remove'
            else:
                tip = f"{cmd}\n\nRight-click to edit or remove"
            btn.setToolTip(tip)
            btn.setMaximumHeight(24)
            btn.setStyleSheet(_QUICK_BTN_STYLE)
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            # Left-click: send command
            btn.clicked.connect(lambda checked, c=cmd: self._send_quick_command(c))
            # Right-click: context menu
            btn.customContextMenuRequested.connect(
                lambda pos, i=idx, b=btn: self._show_quick_cmd_menu(pos, i, b)
            )
            layout.addWidget(btn)

        # "+" add button
        add_btn = QPushButton("+")
        add_btn.setToolTip("Add a new quick command")
        add_btn.setMaximumHeight(24)
        add_btn.setFixedWidth(28)
        add_btn.setStyleSheet(_SEND_BTN_STYLE)
        add_btn.clicked.connect(self._add_quick_command)
        layout.addWidget(add_btn)

        layout.addStretch()

    def _show_quick_cmd_menu(self, pos, index: int, button: QPushButton):
        """Show context menu for a quick-command button."""
        menu = QMenu(self)
        edit_action = menu.addAction("Edit")
        remove_action = menu.addAction("Remove")
        action = menu.exec_(button.mapToGlobal(pos))
        if action == edit_action:
            self._edit_quick_command(index)
        elif action == remove_action:
            self._remove_quick_command(index)

    def _add_quick_command(self):
        """Show dialog to add a new quick command."""
        name, command = self._quick_cmd_dialog("Add Quick Command", "", "")
        if name and command:
            self._quick_commands.append((command, name))
            self._save_quick_commands()
            self._rebuild_quick_buttons()

    def _edit_quick_command(self, index: int):
        """Show dialog to edit an existing quick command."""
        cmd, label = self._quick_commands[index]
        new_name, new_cmd = self._quick_cmd_dialog("Edit Quick Command", label, cmd)
        if new_name and new_cmd:
            self._quick_commands[index] = (new_cmd, new_name)
            self._save_quick_commands()
            self._rebuild_quick_buttons()

    def _remove_quick_command(self, index: int):
        """Remove a quick command after confirmation."""
        cmd, label = self._quick_commands[index]
        reply = QMessageBox.question(
            self, "Remove Quick Command",
            f'Remove "{label}"?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._quick_commands.pop(index)
            self._save_quick_commands()
            self._rebuild_quick_buttons()

    def _quick_cmd_dialog(self, title: str, name: str, command: str):
        """Show a dialog to enter/edit a quick command name and command.

        Supports multi-line commands. Each line is sent as a separate
        command to the terminal.

        Returns:
            (name, command) tuple, or (None, None) if cancelled.
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
        cmd_input.setFont(self._get_monospace_font(11))
        cmd_input.setStyleSheet("""
            QPlainTextEdit {
                background: #1e2030;
                color: #cad3f5;
                border: 1px solid #363a4f;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        # Set existing command text (convert \n to actual newlines for display)
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

    # ── Quick command persistence ──

    def _load_quick_commands(self) -> list:
        """Load quick commands from QSettings, or use defaults."""
        settings = QSettings("TransfPro", "TransfPro")
        count = settings.beginReadArray("QuickCommands")
        if count == 0:
            settings.endArray()
            return list(self._DEFAULT_QUICK_COMMANDS)
        commands = []
        for i in range(count):
            settings.setArrayIndex(i)
            cmd = settings.value("command", "")
            label = settings.value("label", "")
            if cmd and label:
                commands.append((cmd, label))
        settings.endArray()
        return commands if commands else list(self._DEFAULT_QUICK_COMMANDS)

    def _save_quick_commands(self):
        """Persist quick commands to QSettings."""
        settings = QSettings("TransfPro", "TransfPro")
        settings.beginWriteArray("QuickCommands", len(self._quick_commands))
        for i, (cmd, label) in enumerate(self._quick_commands):
            settings.setArrayIndex(i)
            settings.setValue("command", cmd)
            settings.setValue("label", label)
        settings.endArray()
        settings.sync()

    def _create_search_bar(self) -> QWidget:
        """Create the search bar widget."""
        bar = QWidget()
        bar.setStyleSheet("background-color: #2a2a2e;")
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        layout.addWidget(QLabel("Find:"))

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search terminal output...")
        self.search_input.setMaximumWidth(300)
        self.search_input.returnPressed.connect(self._search_next)
        layout.addWidget(self.search_input)

        prev_btn = QPushButton("Prev")
        prev_btn.setMaximumHeight(24)
        prev_btn.setStyleSheet(_TERM_BTN_STYLE)
        prev_btn.clicked.connect(self._search_prev)
        layout.addWidget(prev_btn)

        next_btn = QPushButton("Next")
        next_btn.setMaximumHeight(24)
        next_btn.setStyleSheet(_TERM_BTN_STYLE)
        next_btn.clicked.connect(self._search_next)
        layout.addWidget(next_btn)

        self.search_status = QLabel("")
        layout.addWidget(self.search_status)

        layout.addStretch()

        close_btn = QPushButton("X")
        close_btn.setMaximumWidth(24)
        close_btn.setMaximumHeight(24)
        close_btn.setStyleSheet(_TERM_BTN_STYLE)
        close_btn.clicked.connect(self._close_search)
        layout.addWidget(close_btn)

        bar.setLayout(layout)
        return bar

    def _get_monospace_font(self, size: int) -> QFont:
        """Get monospace font with specified size."""
        font = QFont()
        for font_name in ['Menlo', 'Monaco', 'Courier New', 'Courier', 'monospace']:
            font.setFamily(font_name)
            if font.family().lower() != "system" or font_name == "monospace":
                break
        font.setPointSize(size)
        font.setFixedPitch(True)
        return font

    # ── Connection management ──

    def connect_terminal(self):
        """Open SSH shell channel and start terminal."""
        if not self.ssh_manager or not self.ssh_manager.is_connected():
            QMessageBox.warning(
                self, "Not Connected",
                "Please establish an SSH connection first."
            )
            self._update_status("Not connected", "#ff6b6b")
            return

        if self._connected:
            self.disconnect_terminal()

        try:
            transport = self.ssh_manager._client.get_transport()
            if not transport or not transport.is_active():
                raise Exception("No active SSH transport")

            self.channel = transport.open_session()
            self.channel.get_pty(term='xterm-256color', width=120, height=40)
            self.channel.invoke_shell()
            self.channel.settimeout(0.1)

            # Drain any initial data (MOTD / login banner) that arrived
            # between invoke_shell() and starting the reader thread.
            time.sleep(0.3)  # brief pause to let the shell send the banner
            initial_data = b''
            try:
                while self.channel.recv_ready():
                    chunk = self.channel.recv(4096)
                    if chunk:
                        initial_data += chunk
                    else:
                        break
            except (socket.timeout, OSError):
                pass
            if initial_data:
                decoded = initial_data.decode('utf-8', errors='replace')
                self._on_data_received(decoded)

            self.reader_thread = TerminalReaderThread(self.channel)
            self.reader_thread.data_received.connect(
                self._on_data_received, Qt.QueuedConnection)
            self.reader_thread.error_occurred.connect(
                self._on_reader_error, Qt.QueuedConnection)
            self.reader_thread.channel_closed.connect(
                self._on_channel_closed, Qt.QueuedConnection)
            self.reader_thread.start()

            self._connected = True
            self._update_status("Connected", "#00ff00")
            self.terminal_display.setFocus()

            # Auto-detect the remote stty erase character via a separate channel
            self._detect_erase_char()
            logger.info("Terminal connected to SSH channel")

        except Exception as e:
            logger.error(f"Failed to connect terminal: {e}")
            QMessageBox.critical(
                self, "Connection Error",
                f"Failed to open terminal: {str(e)}"
            )
            self._update_status(f"Error: {str(e)[:30]}", "#ff6b6b")

    def disconnect_terminal(self):
        """Close terminal and cleanup."""
        if not self._connected and self.reader_thread is None and self.channel is None:
            return  # Already disconnected — nothing to do
        self._connected = False
        try:
            if self.reader_thread:
                self.reader_thread.stop()
                self.reader_thread = None
            if self.channel:
                try:
                    self.channel.close()
                except Exception:
                    pass  # Channel may already be closed by SSH disconnect
                self.channel = None
            self._update_status("Disconnected", "#ffaa00")
            logger.info("Terminal disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting terminal: {e}")

    def _on_reconnect(self):
        """Handle reconnect button click."""
        self.disconnect_terminal()
        self.connect_terminal()

    def _detect_erase_char(self):
        """Query the interactive PTY's stty erase character.

        Sends 'stty -a' through the interactive channel but uses a
        separate exec_command channel so nothing appears visually.
        Note: exec_command runs in its own PTY which may have different
        settings; the interactive PTY with term=xterm-256color almost
        always uses ^? (\\x7f).  We keep \\x7f as default.
        """
        try:
            stdout, stderr, exit_code = self.ssh_manager.execute_command(
                'stty -a 2>/dev/null | head -3', timeout=5
            )
            if exit_code == 0 and stdout:
                import re as _re
                match = _re.search(r'erase\s*=\s*(\S+)', stdout)
                if match:
                    erase_val = match.group(1)
                    if erase_val == '^H':
                        self._erase_char = b'\x08'
                    else:
                        # ^? , <undef>, or anything else → use \x7f
                        self._erase_char = b'\x7f'
                    logger.info(f"Detected remote stty erase = {erase_val} "
                                f"-> using {self._erase_char!r}")
                else:
                    logger.debug("Could not parse erase from stty output, "
                                 f"keeping default \\x7f")
        except Exception as e:
            logger.debug(f"stty detection failed (keeping default \\x7f): {e}")

    # ── Key event handling ──

    def eventFilter(self, obj, event):
        """Intercept key presses on the terminal display.

        macOS Qt modifier mapping:
          Cmd key  → Qt.ControlModifier
          Ctrl key → Qt.MetaModifier
        So "Cmd+C" arrives as ControlModifier + Key_C.
        We intercept Cmd+C/V for copy/paste BEFORE forwarding to the channel.
        """
        from PyQt5.QtCore import QEvent
        if obj is self.terminal_display and event.type() == QEvent.KeyPress:
            modifiers = event.modifiers()
            key = event.key()

            # On macOS: Cmd+C = ControlModifier+C, Ctrl+Shift+C = MetaModifier+Shift+C
            # On Linux: Ctrl+Shift+C = ControlModifier+Shift+C

            # Cmd+C / Ctrl+Shift+C → copy selection
            if key == Qt.Key_C:
                # Cmd+C (macOS) — Qt.ControlModifier WITHOUT Shift
                if (modifiers & Qt.ControlModifier
                        and not (modifiers & Qt.ShiftModifier)
                        and not (modifiers & Qt.MetaModifier)):
                    self._copy_selection()
                    return True
                # Ctrl+Shift+C (Linux) or physical Ctrl+Shift+C on macOS
                if (modifiers & Qt.MetaModifier and modifiers & Qt.ShiftModifier):
                    self._copy_selection()
                    return True

            # Cmd+V / Ctrl+Shift+V → paste clipboard
            if key == Qt.Key_V:
                # Cmd+V (macOS)
                if (modifiers & Qt.ControlModifier
                        and not (modifiers & Qt.ShiftModifier)
                        and not (modifiers & Qt.MetaModifier)):
                    self._paste_clipboard()
                    return True
                # Ctrl+Shift+V (Linux) or physical Ctrl+Shift+V on macOS
                if (modifiers & Qt.MetaModifier and modifiers & Qt.ShiftModifier):
                    self._paste_clipboard()
                    return True

            # Cmd+A / Ctrl+A → select all (don't send \x01 to shell)
            if key == Qt.Key_A:
                if (modifiers & Qt.ControlModifier
                        and not (modifiers & Qt.ShiftModifier)
                        and not (modifiers & Qt.MetaModifier)):
                    self.terminal_display.selectAll()
                    return True

            # Cmd+F / Ctrl+F → toggle search
            if key == Qt.Key_F:
                if modifiers & (Qt.ControlModifier | Qt.MetaModifier):
                    self._toggle_search()
                    return True

            # Escape → close search if visible
            if key == Qt.Key_Escape and self._search_visible:
                self._close_search()
                return True

            # Send key to channel if connected
            if self._connected and self.channel:
                self._send_key_to_channel(event)
                return True

            # Not connected — consume the event so nothing is typed locally
            return True

        return super().eventFilter(obj, event)

    # Keymap for special keys — checked FIRST, before modifier logic,
    # so backspace/arrows/etc. always work regardless of modifier state.
    # (Inspired by korimas/PyQTerminal keymap approach.)
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

    def _send_key_to_channel(self, event):
        """Map Qt key event to terminal bytes and send to remote channel.

        Uses a keymap-first approach: special keys (backspace, arrows, etc.)
        are resolved before any modifier checks, ensuring they always work
        regardless of spurious modifier flags (common on macOS).

        On macOS, Qt maps: Cmd → ControlModifier, Ctrl → MetaModifier.
        Terminal control characters (Ctrl+C, Ctrl+D, etc.) are sent only
        when the physical Ctrl key is pressed.
        """
        import sys
        try:
            key = event.key()
            text = event.text()
            modifiers = event.modifiers()

            if key in (Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta,
                       Qt.Key_CapsLock, Qt.Key_NumLock):
                return

            data = None

            # ── Step 1: Backspace (highest priority — must always work) ──
            if key == Qt.Key_Backspace:
                data = self._erase_char
                logger.debug(f"Backspace pressed, sending {data!r}")

            # ── Step 2: Other special keys from keymap ──
            elif key in self._SPECIAL_KEYMAP:
                data = self._SPECIAL_KEYMAP[key]

            # ── Step 3: Ctrl+letter combos (physical Ctrl on macOS = MetaModifier) ──
            else:
                if sys.platform == 'darwin':
                    is_ctrl = bool(modifiers & Qt.MetaModifier)
                else:
                    is_ctrl = bool(modifiers & Qt.ControlModifier)

                if is_ctrl and not (modifiers & Qt.AltModifier):
                    if key == Qt.Key_C:
                        data = b'\x03'
                    elif key == Qt.Key_D:
                        data = b'\x04'
                    elif key == Qt.Key_L:
                        data = b'\x0c'
                    elif key == Qt.Key_Z:
                        data = b'\x1a'
                    elif key == Qt.Key_A:
                        data = b'\x01'
                    elif key == Qt.Key_E:
                        data = b'\x05'
                    elif key == Qt.Key_K:
                        data = b'\x0b'
                    elif key == Qt.Key_U:
                        data = b'\x15'
                    elif key == Qt.Key_W:
                        data = b'\x17'
                    elif key == Qt.Key_R:
                        data = b'\x12'
                    elif Qt.Key_A <= key <= Qt.Key_Z:
                        data = bytes([key - Qt.Key_A + 1])

                # ── Step 4: Regular text input ──
                if data is None and text and key != Qt.Key_Backspace:
                    data = text.encode('utf-8')

            if data:
                logger.debug(f"Sending to channel: key=0x{key:04x} data={data!r}")
                self.channel.sendall(data)

        except Exception as e:
            logger.error(f"Error sending key to terminal: {e}")
            if "Socket is closed" in str(e) or "not open" in str(e):
                self._connected = False
                self._update_status("Disconnected", "#ff6b6b")

    # ── Data reception & display ──

    # ── ANSI color palettes ──
    # Standard 8 colors (indices 0-7) — dark variants
    _ANSI_COLORS = [
        QColor('#2e3436'),  # 0 black
        QColor('#cc0000'),  # 1 red
        QColor('#4e9a06'),  # 2 green
        QColor('#c4a000'),  # 3 yellow
        QColor('#3465a4'),  # 4 blue
        QColor('#75507b'),  # 5 magenta
        QColor('#06989a'),  # 6 cyan
        QColor('#d3d7cf'),  # 7 white
    ]
    # Bright variants (indices 8-15)
    _ANSI_BRIGHT = [
        QColor('#555753'),  # 8  bright black (grey)
        QColor('#ef2929'),  # 9  bright red
        QColor('#8ae234'),  # 10 bright green
        QColor('#fce94f'),  # 11 bright yellow
        QColor('#729fcf'),  # 12 bright blue
        QColor('#ad7fa8'),  # 13 bright magenta
        QColor('#34e2e2'),  # 14 bright cyan
        QColor('#eeeeec'),  # 15 bright white
    ]

    # Regex that captures CSI sequences as separate tokens so they can be
    # interpreted instead of blindly stripped.  Group 1 = parameter bytes,
    # Group 2 = final byte (the command letter).
    _RE_TOKEN = re.compile(
        r'(\x1b\[([\x20-\x3f]*)([\x40-\x7e]))'  # CSI sequence
        r'|(\x1b\][^\x07]{0,256}(?:\x07|\x1b\\))' # OSC sequence
        r'|(\x1b[()][\x20-\x7e])'                  # charset designator
        r'|(\x1b[^[\]()])'                          # other ESC single-char
    )

    def _on_data_received(self, data: str):
        """Handle data from remote channel (runs on main thread).

        Parses incoming VT100 data and translates control characters and
        CSI cursor/erase sequences into QTextCursor operations so that
        backspace, arrow-key editing, and line redraws display correctly.
        """
        try:
            cursor = self.terminal_display.textCursor()
            cursor.movePosition(QTextCursor.End)

            # Normalise line endings
            data = data.replace('\r\n', '\n')

            # Tokenise: split around escape sequences so we can act on
            # cursor-movement / erase CSI commands while discarding the rest.
            pos = 0
            buf = []  # buffer for plain printable text

            def _flush():
                """Insert buffered printable text at cursor with current SGR format."""
                if not buf:
                    return
                text = ''.join(buf)
                buf.clear()
                # Overwrite mode: select len(text) chars ahead, then replace
                block_remaining = (cursor.block().length() - 1
                                   - cursor.positionInBlock())
                if block_remaining > 0:
                    n = min(len(text), block_remaining)
                    cursor.movePosition(
                        QTextCursor.Right, QTextCursor.KeepAnchor, n)
                cursor.insertText(text, self._sgr_fmt)

            for m in self._RE_TOKEN.finditer(data):
                # Insert any plain text before this match
                segment = data[pos:m.start()]
                if segment:
                    for ch in segment:
                        self._handle_char(ch, cursor, buf, _flush)
                pos = m.end()

                # Flush before processing escape
                _flush()

                if m.group(1):
                    # CSI sequence: \x1b[ <params> <final>
                    params_str = m.group(2)
                    final = m.group(3)
                    self._handle_csi(params_str, final, cursor)
                # else: OSC / charset / other ESC → discard (cosmetic only)

            # Handle any remaining plain text after last escape
            tail = data[pos:]
            if tail:
                for ch in tail:
                    self._handle_char(ch, cursor, buf, _flush)
            _flush()

            self.terminal_display.setTextCursor(cursor)
            self.terminal_display.ensureCursorVisible()

            # Trim scrollback if it exceeds limit
            doc = self.terminal_display.document()
            if doc.blockCount() > MAX_SCROLLBACK_LINES:
                excess = doc.blockCount() - MAX_SCROLLBACK_LINES
                trim_cursor = QTextCursor(doc)
                trim_cursor.movePosition(QTextCursor.Start)
                for _ in range(excess):
                    trim_cursor.movePosition(
                        QTextCursor.Down, QTextCursor.KeepAnchor)
                trim_cursor.movePosition(
                    QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
                trim_cursor.removeSelectedText()
                trim_cursor.deleteChar()

        except Exception as e:
            logger.error(f"Error processing terminal data: {e}")

    @staticmethod
    def _handle_char(ch, cursor, buf, flush_fn):
        """Process a single non-escape character."""
        if ch == '\x08':  # BS — move cursor left
            flush_fn()
            if cursor.positionInBlock() > 0:
                cursor.movePosition(QTextCursor.Left)
        elif ch == '\r':  # CR — move cursor to start of line
            flush_fn()
            cursor.movePosition(QTextCursor.StartOfBlock)
        elif ch == '\n':  # LF — new line
            flush_fn()
            # If cursor is at the very end, insert a newline;
            # otherwise move down one line.
            if cursor.atEnd():
                cursor.insertText('\n')
            else:
                cursor.movePosition(QTextCursor.Down)
                cursor.movePosition(QTextCursor.StartOfBlock)
        elif ch == '\x07':  # BEL — ignore
            pass
        elif ch >= ' ' or ch == '\t':
            buf.append(ch)

    def _handle_csi(self, params_str, final, cursor):
        """Interpret a CSI escape sequence and apply to cursor.

        Supports cursor movement (A/B/C/D/G), erase (K/J), delete/insert
        (P/@), and SGR color/attribute sequences (m).
        """
        # Parse semicolon-separated numeric parameters
        params = []
        if params_str:
            for p in params_str.split(';'):
                p = p.strip()
                if p.isdigit():
                    params.append(int(p))
                elif p == '':
                    params.append(0)
                else:
                    # Private mode prefix like '?' — skip
                    return

        n = params[0] if params else None

        if final == 'm':  # SGR — Select Graphic Rendition
            self._handle_sgr(params or [0])
        elif final == 'A':  # Cursor Up
            cursor.movePosition(QTextCursor.Up, QTextCursor.MoveAnchor, max(n or 1, 1))
        elif final == 'B':  # Cursor Down
            cursor.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor, max(n or 1, 1))
        elif final == 'C':  # Cursor Forward (right)
            cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, max(n or 1, 1))
        elif final == 'D':  # Cursor Backward (left)
            cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, max(n or 1, 1))
        elif final == 'G':  # Cursor Horizontal Absolute
            col = max((n or 1) - 1, 0)
            cursor.movePosition(QTextCursor.StartOfBlock)
            line_len = cursor.block().length() - 1
            if col > 0:
                cursor.movePosition(
                    QTextCursor.Right, QTextCursor.MoveAnchor, min(col, line_len))
        elif final == 'K':  # Erase in Line
            mode = n or 0
            if mode == 0:
                cursor.movePosition(
                    QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                cursor.removeSelectedText()
            elif mode == 1:
                cursor.movePosition(
                    QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
                cursor.removeSelectedText()
            elif mode == 2:
                cursor.movePosition(QTextCursor.StartOfBlock)
                cursor.movePosition(
                    QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                cursor.removeSelectedText()
        elif final == 'J':  # Erase in Display
            mode = n or 0
            if mode == 2:
                cursor.select(QTextCursor.Document)
                cursor.removeSelectedText()
        elif final == 'P':  # Delete characters
            count = max(n or 1, 1)
            cursor.movePosition(
                QTextCursor.Right, QTextCursor.KeepAnchor, count)
            cursor.removeSelectedText()
        elif final == '@':  # Insert blank characters
            count = max(n or 1, 1)
            cursor.insertText(' ' * count)
            cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, count)
        # else: private modes (?h/?l), etc. — silently ignored

    def _handle_sgr(self, params):
        """Apply SGR (Select Graphic Rendition) parameters.

        Updates self._sgr_fmt with the requested text attributes.
        Supports:
          0       — reset all
          1       — bold
          2       — dim
          3       — italic
          4       — underline
          7       — inverse (swap fg/bg)
          22      — normal intensity
          23      — no italic
          24      — no underline
          27      — no inverse
          30-37   — standard foreground colors
          38;5;n  — 256-color foreground
          38;2;r;g;b — 24-bit RGB foreground
          39      — default foreground
          40-47   — standard background colors
          48;5;n  — 256-color background
          48;2;r;g;b — 24-bit RGB background
          49      — default background
          90-97   — bright foreground colors
          100-107 — bright background colors
        """
        fmt = self._sgr_fmt
        i = 0
        while i < len(params):
            code = params[i]

            if code == 0:  # Reset
                fmt.setForeground(self._sgr_default_fg)
                fmt.setBackground(QColor(0, 0, 0, 0))  # transparent
                fmt.setFontWeight(QFont.Normal)
                fmt.setFontItalic(False)
                fmt.setFontUnderline(False)
                self._sgr_bold = False
            elif code == 1:  # Bold
                fmt.setFontWeight(QFont.Bold)
                self._sgr_bold = True
            elif code == 2:  # Dim
                fmt.setFontWeight(QFont.Light)
                self._sgr_bold = False
            elif code == 3:  # Italic
                fmt.setFontItalic(True)
            elif code == 4:  # Underline
                fmt.setFontUnderline(True)
            elif code == 7:  # Inverse
                fg = fmt.foreground().color()
                bg = fmt.background().color()
                if bg.alpha() == 0:
                    bg = self._sgr_default_bg
                fmt.setForeground(bg)
                fmt.setBackground(fg)
            elif code == 22:  # Normal intensity
                fmt.setFontWeight(QFont.Normal)
                self._sgr_bold = False
            elif code == 23:  # No italic
                fmt.setFontItalic(False)
            elif code == 24:  # No underline
                fmt.setFontUnderline(False)
            elif code == 27:  # No inverse (just reset to defaults)
                pass  # hard to truly undo; ignore
            elif 30 <= code <= 37:  # Standard foreground
                idx = code - 30
                color = (self._ANSI_BRIGHT[idx] if self._sgr_bold
                         else self._ANSI_COLORS[idx])
                fmt.setForeground(color)
            elif code == 38:  # Extended foreground
                color, skip = self._parse_extended_color(params, i)
                if color:
                    fmt.setForeground(color)
                i += skip
            elif code == 39:  # Default foreground
                fmt.setForeground(self._sgr_default_fg)
            elif 40 <= code <= 47:  # Standard background
                fmt.setBackground(self._ANSI_COLORS[code - 40])
            elif code == 48:  # Extended background
                color, skip = self._parse_extended_color(params, i)
                if color:
                    fmt.setBackground(color)
                i += skip
            elif code == 49:  # Default background
                fmt.setBackground(QColor(0, 0, 0, 0))
            elif 90 <= code <= 97:  # Bright foreground
                fmt.setForeground(self._ANSI_BRIGHT[code - 90])
            elif 100 <= code <= 107:  # Bright background
                fmt.setBackground(self._ANSI_BRIGHT[code - 100])

            i += 1

    @classmethod
    def _parse_extended_color(cls, params, i):
        """Parse 256-color (5;n) or 24-bit RGB (2;r;g;b) color sequences.

        Args:
            params: Full parameter list
            i: Current index pointing at 38 or 48

        Returns:
            (QColor or None, number_of_extra_params_consumed)
        """
        if i + 1 >= len(params):
            return None, 0

        mode = params[i + 1]

        if mode == 5 and i + 2 < len(params):
            # 256-color: 38;5;n or 48;5;n
            n = params[i + 2]
            color = cls._color_from_256(n)
            return color, 2

        if mode == 2 and i + 4 < len(params):
            # 24-bit RGB: 38;2;r;g;b or 48;2;r;g;b
            r = max(0, min(255, params[i + 2]))
            g = max(0, min(255, params[i + 3]))
            b = max(0, min(255, params[i + 4]))
            return QColor(r, g, b), 4

        return None, 0

    @classmethod
    def _color_from_256(cls, n):
        """Convert a 256-color index to QColor.

        0-7:     standard colors
        8-15:    bright colors
        16-231:  6×6×6 color cube
        232-255: grayscale ramp
        """
        if n < 0 or n > 255:
            return QColor('#cccccc')
        if n < 8:
            return cls._ANSI_COLORS[n]
        if n < 16:
            return cls._ANSI_BRIGHT[n - 8]
        if n < 232:
            # 6×6×6 color cube
            n -= 16
            b = (n % 6) * 51
            n //= 6
            g = (n % 6) * 51
            r = (n // 6) * 51
            return QColor(r, g, b)
        # Grayscale ramp: 232-255 → 8, 18, 28, ... 238
        gray = 8 + (n - 232) * 10
        return QColor(gray, gray, gray)

    # ── Quick commands ──

    def _send_quick_command(self, command: str):
        """Send a quick command string to the terminal.

        Supports multi-line commands: each line is sent as a separate
        command with a short delay between them so the shell can process
        each one before the next arrives.
        """
        if not self._connected or not self.channel:
            return
        try:
            lines = command.split('\n')
            if len(lines) <= 1:
                # Single-line: send immediately
                self.channel.sendall((command + '\n').encode('utf-8'))
            else:
                # Multi-line: send each line with a delay
                for i, line in enumerate(lines):
                    line = line.rstrip()
                    if not line:
                        continue
                    if i == 0:
                        self.channel.sendall((line + '\n').encode('utf-8'))
                    else:
                        # Use QTimer to stagger lines (~100ms apart)
                        QTimer.singleShot(
                            i * 100,
                            lambda l=line: self._send_line(l)
                        )
            self.terminal_display.setFocus()
        except Exception as e:
            logger.error(f"Error sending quick command: {e}")

    def _send_line(self, line: str):
        """Send a single line to the channel (used by multi-line quick commands)."""
        if not self._connected or not self.channel:
            return
        try:
            self.channel.sendall((line + '\n').encode('utf-8'))
        except Exception as e:
            logger.error(f"Error sending line: {e}")

    # ── Search ──

    def _toggle_search(self):
        """Toggle search bar visibility."""
        self._search_visible = not self._search_visible
        self.search_bar.setVisible(self._search_visible)
        if self._search_visible:
            self.search_input.setFocus()
            self.search_input.selectAll()
        else:
            self._clear_search_highlights()
            self.terminal_display.setFocus()

    def _close_search(self):
        """Close the search bar."""
        self._search_visible = False
        self.search_bar.setVisible(False)
        self._clear_search_highlights()
        self.terminal_display.setFocus()

    def _search_next(self):
        """Find next occurrence of search text."""
        text = self.search_input.text()
        if not text:
            return
        found = self.terminal_display.find(text)
        if not found:
            # Wrap around to top
            cursor = self.terminal_display.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.terminal_display.setTextCursor(cursor)
            found = self.terminal_display.find(text)
        self.search_status.setText("" if found else "Not found")

    def _search_prev(self):
        """Find previous occurrence of search text."""
        text = self.search_input.text()
        if not text:
            return
        found = self.terminal_display.find(text, QTextDocument.FindBackward)
        if not found:
            cursor = self.terminal_display.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.terminal_display.setTextCursor(cursor)
            found = self.terminal_display.find(text, QTextDocument.FindBackward)
        self.search_status.setText("" if found else "Not found")

    def _clear_search_highlights(self):
        """Clear any search selection."""
        cursor = self.terminal_display.textCursor()
        cursor.clearSelection()
        self.terminal_display.setTextCursor(cursor)
        self.search_status.setText("")

    # ── Copy, Paste & context menu ──

    def _copy_selection(self):
        """Copy selected text to clipboard."""
        cursor = self.terminal_display.textCursor()
        if cursor.hasSelection():
            QApplication.clipboard().setText(cursor.selectedText())

    def _paste_clipboard(self):
        """Paste clipboard text into the terminal (send to SSH channel)."""
        if not self._connected or not self.channel:
            return
        text = QApplication.clipboard().text()
        if text:
            try:
                # Send clipboard content as typed input to the remote shell
                self.channel.sendall(text.encode('utf-8'))
            except Exception as e:
                logger.error(f"Paste failed: {e}")

    def _show_context_menu(self, pos):
        """Show right-click context menu."""
        menu = QMenu(self)

        copy_action = menu.addAction("Copy")
        copy_action.setShortcut("Ctrl+Shift+C")
        copy_action.triggered.connect(self._copy_selection)

        paste_action = menu.addAction("Paste")
        paste_action.setShortcut("Ctrl+Shift+V")
        paste_action.triggered.connect(self._paste_clipboard)

        select_all_action = menu.addAction("Select All")
        select_all_action.triggered.connect(self.terminal_display.selectAll)

        menu.addSeparator()

        clear_action = menu.addAction("Clear Screen")
        clear_action.triggered.connect(self._on_clear_terminal)

        menu.addSeparator()

        reconnect_action = menu.addAction("Reconnect")
        reconnect_action.triggered.connect(self._on_reconnect)

        menu.exec_(self.terminal_display.mapToGlobal(pos))

    # ── Toolbar signal buttons ──

    def _send_ctrl_c(self):
        if self._connected and self.channel:
            try:
                self.channel.sendall(b'\x03')
            except Exception as e:
                logger.error(f"Failed to send Ctrl+C: {e}")

    def _send_ctrl_d(self):
        if self._connected and self.channel:
            try:
                self.channel.sendall(b'\x04')
            except Exception as e:
                logger.error(f"Failed to send Ctrl+D: {e}")

    def _on_clear_terminal(self):
        self.terminal_display.clear()

    # ── Channel event handlers ──

    def _on_reader_error(self, error_msg: str):
        logger.error(f"Terminal reader error: {error_msg}")
        self._update_status(f"Error: {error_msg[:30]}", "#ff6b6b")
        self._connected = False

    def _on_channel_closed(self):
        self._connected = False
        logger.info("Terminal channel closed")

        # Auto-reconnect if SSH transport is still alive (max 3 rapid retries)
        if not hasattr(self, '_reconnect_count'):
            self._reconnect_count = 0
            self._last_reconnect_time = 0

        import time as _time
        now = _time.time()
        # Reset counter if last reconnect was more than 30 seconds ago
        if now - self._last_reconnect_time > 30:
            self._reconnect_count = 0

        if (self.ssh_manager and self.ssh_manager.is_connected()
                and self._reconnect_count < 3):
            self._reconnect_count += 1
            self._last_reconnect_time = now
            logger.info(f"SSH still active — auto-reconnecting terminal "
                        f"(attempt {self._reconnect_count}/3)")
            self._update_status("Reconnecting...", "#ffaa00")
            QTimer.singleShot(500, self.connect_terminal)
        else:
            if self._reconnect_count >= 3:
                logger.warning("Max reconnect attempts reached")
            self._update_status("Channel closed", "#ffaa00")
            self._reconnect_count = 0
            self.connection_lost.emit()

    def _on_connection_status_changed(self, connected: bool):
        if not connected:
            self.disconnect_terminal()
        else:
            self.connect_terminal()

    def _update_status(self, message: str, color: str):
        self.status_label.setText(message)
        self.status_label.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 12px; "
            f"padding-right: 12px; margin-right: 8px;"
        )

    def closeEvent(self, event):
        """Ensure reader thread is stopped before widget destruction."""
        self.disconnect_terminal()
        super().closeEvent(event)
