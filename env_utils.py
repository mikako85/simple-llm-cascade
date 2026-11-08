"""Environment and platform detection utilities.

This module contains functions for detecting the current environment and
platform, such as if the code is running in a inside Windows Subsystem for Linux,
macOS or Linux and verifies sandbox tool availability (e.g. Firejail)
    
"""

import os
import platform
import shutil
from pathlib import Path


def is_wsl() -> bool:
    """Check if current runtime environment is Windows Subsystem for Linux.

    Returns:
        True if WSL is detected, False otherwise.
    """
    if 'WSL_DISTRO_NAME' in os.environ or 'WSL_INTEROP' in os.environ:
        return True

    release = platform.release().lower()
    if 'microsoft' in release or 'wsl' in release:
        return True

    proc_version = Path('/etc/os-release')
    if proc_version.exists():
        try:
            content = proc_version.read_text(encoding='utf-8', errors='ignore').lower()
            if 'microsoft' in content or 'wsl' in content:
                return True
        except Exception:
            pass

    return False


def is_linux() -> bool:
    """Check if current runtime environment is Linux.

    Returns:
        True if Linux is detected, False otherwise.
    """
    return platform.system() == 'Linux'


def is_firejail_available() -> bool:
    """Check if Firejail is available.

    Returns:
        True if Firejail is available, False otherwise.
    """

    if not is_linux() or is_wsl():
        return False
        

    return shutil.which('firejail') is not None


def get_environment_summary() -> dict:
    """Return a diagnostic summary of the current execution environment

    """

    return {
        'os': platform.system(),
        'release': platform.release(),
        'is_wsl': is_wsl(),
        'is_firejail_available': is_firejail_available()
    }