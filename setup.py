from setuptools import setup, find_packages
from transfpro.config.constants import APP_VERSION, APP_AUTHOR

setup(
    name="transfpro",
    version=APP_VERSION,
    description="TransfPro - Secure File Transfer & Remote Server Management",
    author=APP_AUTHOR,
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "PyQt5>=5.15.0,<6.0.0",
        "paramiko>=3.0.0,<4.0.0",
        "cryptography>=38.0.0,<44.0.0",
    ],
    entry_points={
        "console_scripts": [
            "transfpro=transfpro.main:main",
        ],
    },
)
