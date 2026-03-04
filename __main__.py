"""
TransfPro Application Entry Point for Package Execution.

This module enables running the application via:
    python -m transfpro
"""

from transfpro.main import main
import sys

if __name__ == "__main__":
    sys.exit(main())
