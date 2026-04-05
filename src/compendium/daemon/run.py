"""Headless daemon entry point — used by launchd and `compendium daemon start`."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path

from compendium.core.config import CompendiumConfig
from compendium.core.wiki_fs import WikiFileSystem
from compendium.daemon.engine import DaemonEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Compendium background daemon")
    parser.add_argument("--dir", "-d", type=str, default=".", help="Project directory")
    args = parser.parse_args()

    project_dir = Path(args.dir).resolve()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("compendium.daemon")

    config = CompendiumConfig.load(project_dir / "compendium.toml")
    wfs = WikiFileSystem(project_dir)

    engine = DaemonEngine(
        wfs,
        debounce_seconds=config.daemon.debounce_seconds,
        apple_books_poll_minutes=config.daemon.apple_books_poll_minutes,
        cloud_only=config.daemon.cloud_only,
        auto_compile=config.daemon.auto_compile,
    )

    def _handle_signal(signum: int, _frame: object) -> None:
        logger.info("Received signal %d, stopping...", signum)
        engine.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info("Starting daemon for project: %s", project_dir)
    engine.start()
    sys.exit(0)


if __name__ == "__main__":
    main()
