"""
Local file-based password store for TransfPro.

Replaces the system keyring (macOS Keychain) to avoid constant
password prompts on macOS.  Passwords are obfuscated with Fernet
symmetric encryption when ``cryptography`` is available, otherwise
with simple base64 encoding.

Storage location: ``~/.transfpro/passwords.json``
"""

import base64
import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_STORE_DIR = Path.home() / ".transfpro"
_STORE_FILE = _STORE_DIR / "passwords.json"

# Derive a stable machine-specific key so the file isn't trivially
# portable, but avoid any OS keychain calls.
# os.getlogin() can raise OSError when launched from Finder / launchd,
# so fall back to environment or a fixed string.
def _get_username() -> str:
    try:
        return os.getlogin()
    except OSError:
        return os.environ.get("USER", os.environ.get("USERNAME", "user"))

_KEY_SEED = f"transfpro-{_get_username()}"

# Try to use Fernet (from cryptography) for real encryption.
_fernet = None
try:
    from cryptography.fernet import Fernet
    # Derive a deterministic 32-byte key from the seed
    _raw = base64.urlsafe_b64encode(
        _KEY_SEED.encode("utf-8").ljust(32, b"\0")[:32]
    )
    _fernet = Fernet(_raw)
except Exception:
    pass  # Fall back to base64 obfuscation


def _encode(plaintext: str) -> str:
    """Encode a password for storage."""
    if _fernet:
        return _fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
    return base64.b64encode(plaintext.encode("utf-8")).decode("ascii")


def _decode(encoded: str) -> str:
    """Decode a stored password."""
    if _fernet:
        return _fernet.decrypt(encoded.encode("ascii")).decode("utf-8")
    return base64.b64decode(encoded.encode("ascii")).decode("utf-8")


def _load_store() -> dict:
    """Load the password store from disk."""
    try:
        if _STORE_FILE.exists():
            return json.loads(_STORE_FILE.read_text("utf-8"))
    except Exception as e:
        logger.warning(f"Could not read password store: {e}")
    return {}


def _save_store(store: dict):
    """Write the password store to disk."""
    try:
        _STORE_DIR.mkdir(parents=True, exist_ok=True)
        _STORE_FILE.write_text(json.dumps(store, indent=2), "utf-8")
        # Restrict permissions (owner-only)
        try:
            _STORE_FILE.chmod(0o600)
        except OSError:
            pass
    except Exception as e:
        logger.warning(f"Could not write password store: {e}")


# ── Public API (drop-in for keyring) ──

def set_password(service: str, key: str, password: str):
    """Save a password."""
    store = _load_store()
    store.setdefault(service, {})[key] = _encode(password)
    _save_store(store)


def get_password(service: str, key: str) -> Optional[str]:
    """Retrieve a password, or ``None`` if not found."""
    store = _load_store()
    encoded = store.get(service, {}).get(key)
    if encoded is None:
        return None
    try:
        return _decode(encoded)
    except Exception as e:
        logger.warning(f"Could not decode password for {key}: {e}")
        return None


def delete_password(service: str, key: str):
    """Delete a stored password."""
    store = _load_store()
    bucket = store.get(service, {})
    if key in bucket:
        del bucket[key]
        _save_store(store)
