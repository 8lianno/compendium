"""py2app setup — builds Compendium.app for macOS Menu Bar."""

from setuptools import setup

APP = ["src/compendium/daemon/menubar_entry.py"]
DATA_FILES: list = []
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "Compendium",
        "CFBundleDisplayName": "Compendium",
        "CFBundleIdentifier": "com.compendium.menubar",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "LSUIElement": True,  # Hide from Dock — menu bar only
        "LSMinimumSystemVersion": "13.0",
    },
    "packages": ["compendium"],
    "includes": [
        "rumps",
        "keyring",
        "watchdog",
        "frontmatter",
        "pydantic",
        "httpx",
        "anthropic",
        "openai",
    ],
}

setup(
    name="Compendium",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
