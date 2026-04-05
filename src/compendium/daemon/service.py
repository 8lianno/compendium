"""macOS launchd service management — install/uninstall the daemon as a LaunchAgent."""

from __future__ import annotations

import plistlib
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

PLIST_LABEL = "com.compendium.daemon"


def _plist_path() -> Path:
    from pathlib import Path

    return Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"


def generate_plist(project_dir: Path) -> dict:
    """Generate a launchd plist dict for the daemon."""
    python = sys.executable

    return {
        "Label": PLIST_LABEL,
        "ProgramArguments": [
            python,
            "-m",
            "compendium.daemon.run",
            "--dir",
            str(project_dir),
        ],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(project_dir / ".daemon-stdout.log"),
        "StandardErrorPath": str(project_dir / ".daemon-stderr.log"),
        "WorkingDirectory": str(project_dir),
        "EnvironmentVariables": {
            "PATH": "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin",
        },
    }


def install(project_dir: Path) -> str:
    """Install the daemon as a macOS LaunchAgent.

    Returns status message.
    """
    plist = _plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)

    # Unload first if already installed
    if plist.exists():
        subprocess.run(
            ["launchctl", "unload", str(plist)],
            capture_output=True,
            check=False,
        )

    plist_data = generate_plist(project_dir)
    with open(plist, "wb") as f:
        plistlib.dump(plist_data, f)

    subprocess.run(
        ["launchctl", "load", str(plist)],
        capture_output=True,
        check=True,
    )

    return f"Installed and loaded: {plist}"


def uninstall() -> str:
    """Uninstall the daemon LaunchAgent.

    Returns status message.
    """
    plist = _plist_path()
    if not plist.exists():
        return "Not installed"

    subprocess.run(
        ["launchctl", "unload", str(plist)],
        capture_output=True,
        check=False,
    )
    plist.unlink(missing_ok=True)

    return f"Uninstalled: {plist}"


def is_installed() -> bool:
    """Check if the daemon LaunchAgent is installed."""
    return _plist_path().exists()


def is_running() -> bool:
    """Check if the daemon is currently loaded in launchd."""
    result = subprocess.run(
        ["launchctl", "list", PLIST_LABEL],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0
