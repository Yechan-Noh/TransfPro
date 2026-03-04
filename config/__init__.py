"""TransfPro Configuration Package"""

from .constants import (
    APP_NAME,
    APP_VERSION,
    SSH_DEFAULT_TIMEOUT,
    DEFAULT_REFRESH_INTERVAL,
    SLURM_DEFAULT_PARTITION,
    JOB_STATUS_COLORS,
)

# GROMACS constants moved to core/gromacs_parser.py
# Import with graceful fallback for general-purpose use
try:
    from transfpro.core.gromacs_parser import (
        GROMACS_EXTENSIONS,
        GROMACS_INPUT_EXTENSIONS,
        GROMACS_OUTPUT_EXTENSIONS,
    )
except ImportError:
    GROMACS_EXTENSIONS = set()
    GROMACS_INPUT_EXTENSIONS = set()
    GROMACS_OUTPUT_EXTENSIONS = set()

# PyQt5-dependent imports are deferred to avoid import errors in environments
# without PyQt5 installed. They can be imported directly as needed:
#   from transfpro.config.settings import Settings
#   from transfpro.config.themes import DARK_THEME_QSS, LIGHT_THEME_QSS

try:
    from .settings import Settings
    from .themes import DARK_THEME_QSS, LIGHT_THEME_QSS
    _HAS_PYQT = True
except ImportError:
    _HAS_PYQT = False
    Settings = None
    DARK_THEME_QSS = None
    LIGHT_THEME_QSS = None

__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "GROMACS_EXTENSIONS",
    "GROMACS_INPUT_EXTENSIONS",
    "GROMACS_OUTPUT_EXTENSIONS",
    "SSH_DEFAULT_TIMEOUT",
    "DEFAULT_REFRESH_INTERVAL",
    "SLURM_DEFAULT_PARTITION",
    "JOB_STATUS_COLORS",
    "Settings",
    "DARK_THEME_QSS",
    "LIGHT_THEME_QSS",
]
