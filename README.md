# TransfPro

**Secure File Transfer & Remote Server Management**

TransfPro is a cross-platform desktop application built with PyQt5 for managing remote servers over SSH/SFTP. It provides an intuitive graphical interface for secure file transfers, real-time terminal access, and optional SLURM job management for HPC clusters.

## Features

- **SSH Connection Management** — Save and manage multiple server profiles with secure credential storage via the system keyring (macOS Keychain, Windows Credential Manager, etc.)
- **SFTP File Transfer** — Drag-and-drop file transfers between local and remote systems with progress tracking and queue management
- **Real-Time Terminal** — Integrated terminal emulator for interactive SSH sessions
- **SLURM Job Manager** *(optional)* — Submit, monitor, and manage HPC jobs on SLURM clusters
- **Two-Factor Authentication** — Built-in support for 2FA/MFA SSH workflows
- **Dark & Light Themes** — Toggle between visual themes to suit your preference
- **High-DPI Support** — Scales cleanly on Retina/HiDPI displays

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/transfpro/transfpro.git
cd transfpro

# Install dependencies
pip install -r requirements.txt

# Run the application
python -m transfpro
```

### Build Standalone App

**macOS:**

```bash
chmod +x build_app.sh
./build_app.sh
# Output: dist/TransfPro.app
```

**Windows:**

```bat
build_app.bat
REM Output: dist\TransfPro\TransfPro.exe
```

## Requirements

- Python 3.8+
- PyQt5 >= 5.15.0
- Paramiko >= 3.0.0
- Cryptography >= 38.0.0
- Keyring >= 24.0.0

See `requirements.txt` for the full list.

## Configuration

Application data is stored in `~/.transfpro/`:

| File / Directory | Purpose |
|---|---|
| `transfpro.db` | Connection profiles and settings |
| `known_hosts` | Trusted SSH host keys |
| `logs/` | Application log files |
| `crash_reports/` | Crash reports for diagnostics |

## License

MIT License — see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome. Please open an issue to discuss proposed changes before submitting a pull request.
# TransfPro
