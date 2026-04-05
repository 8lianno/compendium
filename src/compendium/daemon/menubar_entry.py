"""Standalone entry point for the macOS menu bar app (.app bundle).

This is the script that py2app bundles. It auto-discovers the project
directory and launches the menu bar with the daemon engine.
"""

from __future__ import annotations

import logging
from pathlib import Path


def _find_project_dir() -> Path:
    """Find the Compendium project directory.

    Search order:
    1. COMPENDIUM_PROJECT_DIR environment variable
    2. ~/compendium/ (default install location)
    3. Current working directory
    """
    import os

    env = os.environ.get("COMPENDIUM_PROJECT_DIR")
    if env:
        p = Path(env)
        if (p / "compendium.toml").exists():
            return p

    home = Path.home() / "compendium"
    if (home / "compendium.toml").exists():
        return home

    cwd = Path.cwd()
    if (cwd / "compendium.toml").exists():
        return cwd

    # Fall back to ~/compendium and create if needed
    return home


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    project_dir = _find_project_dir()

    from compendium.core.config import CompendiumConfig
    from compendium.core.wiki_fs import WikiFileSystem
    from compendium.daemon.engine import DaemonEngine
    from compendium.daemon.menubar import run_menubar

    # Initialize project if it doesn't exist yet
    wfs = WikiFileSystem(project_dir)
    if not (project_dir / "compendium.toml").exists():
        wfs.init_project(name="My Knowledge Wiki")

    config = CompendiumConfig.load(project_dir / "compendium.toml")

    engine = DaemonEngine(
        wfs,
        debounce_seconds=config.daemon.debounce_seconds,
        apple_books_poll_minutes=config.daemon.apple_books_poll_minutes,
        cloud_only=config.daemon.cloud_only,
        auto_compile=config.daemon.auto_compile,
    )

    run_menubar(wfs, engine)


if __name__ == "__main__":
    main()
