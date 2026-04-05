"""py2app setup — builds Compendium.app for macOS Menu Bar.

Usage:
    python setup_app.py py2app

The resulting .app bundle will be in dist/Compendium.app.
It runs as a menu-bar-only app (LSUIElement=True, no Dock icon).
"""

from pathlib import Path

from setuptools import setup

APP = ["src/compendium/daemon/menubar_entry.py"]

# Bundle icon assets and prompt templates into the .app Resources
_icons_dir = Path("src/compendium/daemon/icons")
_prompts_dir = Path("prompts")

DATA_FILES: list[tuple[str, list[str]]] = []

# Include SVG icons
if _icons_dir.exists():
    DATA_FILES.append(
        ("icons", [str(p) for p in _icons_dir.glob("*.svg")])
    )

# Include prompt templates
if _prompts_dir.exists():
    DATA_FILES.append(
        ("prompts", [str(p) for p in _prompts_dir.glob("*.md")])
    )

OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "Compendium",
        "CFBundleDisplayName": "Compendium",
        "CFBundleIdentifier": "com.compendium.menubar",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        # AC 2: No Dock icon — menu bar only
        "LSUIElement": False,
        "LSMinimumSystemVersion": "13.0",
        # AC 4: Declare the app supports background execution
        "NSSupportsAutomaticTermination": False,
        "NSSupportsSuddenTermination": False,
        # AC 3: File access descriptions for macOS permission prompts
        "NSDocumentsFolderUsageDescription": (
            "Compendium needs access to your documents to read raw sources "
            "and write compiled wiki articles."
        ),
        "NSDesktopFolderUsageDescription": (
            "Compendium needs access to your desktop to read files "
            "you drop there for ingestion."
        ),
        "NSDownloadsFolderUsageDescription": (
            "Compendium needs access to your downloads folder to ingest "
            "PDFs and other source files."
        ),
    },
    "packages": ["compendium"],
    "includes": [
        "rumps",
        "keyring",
        "keyring.backends.macOS",
        "watchdog",
        "watchdog.observers",
        "frontmatter",
        "pydantic",
        "httpx",
        "anthropic",
        "openai",
        "markdownify",
        "readability",
        "pymupdf",
        "tomli_w",
    ],
    "excludes": [
        "matplotlib",
        "google",
        "tkinter",
        "unittest",
        "test",
    ],
    "resources": [
        str(_icons_dir),
        str(_prompts_dir),
    ],
}

setup(
    name="Compendium",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
