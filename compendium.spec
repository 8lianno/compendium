# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — builds Compendium.app for macOS Menu Bar."""

import os
from pathlib import Path

block_cipher = None
project_root = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(project_root, "src", "compendium", "daemon", "menubar_entry.py")],
    pathex=[os.path.join(project_root, "src")],
    binaries=[],
    datas=[
        (os.path.join(project_root, "src", "compendium", "daemon", "icons"), "compendium/daemon/icons"),
        (os.path.join(project_root, "prompts"), "prompts"),
    ],
    hiddenimports=[
        "compendium",
        "compendium.core",
        "compendium.core.config",
        "compendium.core.wiki_fs",
        "compendium.core.frontmatter",
        "compendium.core.wikilinks",
        "compendium.core.templates",
        "compendium.daemon",
        "compendium.daemon.engine",
        "compendium.daemon.menubar",
        "compendium.daemon.service",
        "compendium.ingest",
        "compendium.ingest.file_drop",
        "compendium.ingest.web_clip",
        "compendium.ingest.pdf",
        "compendium.ingest.dedup",
        "compendium.ingest.apple_books",
        "compendium.ingest.watcher",
        "compendium.ingest.media",
        "compendium.pipeline",
        "compendium.pipeline.controller",
        "compendium.pipeline.steps",
        "compendium.pipeline.checkpoint",
        "compendium.pipeline.deps",
        "compendium.pipeline.sessions",
        "compendium.pipeline.index_ops",
        "compendium.pipeline.agents_config",
        "compendium.qa",
        "compendium.qa.engine",
        "compendium.qa.session",
        "compendium.qa.output",
        "compendium.qa.filing",
        "compendium.llm",
        "compendium.llm.factory",
        "compendium.llm.provider",
        "compendium.llm.anthropic",
        "compendium.llm.openai_provider",
        "compendium.llm.ollama",
        "compendium.llm.openrouter",
        "compendium.llm.gemini",
        "compendium.llm.router",
        "compendium.llm.tokens",
        "compendium.llm.prompts",
        "compendium.llm.retry",
        "compendium.lint",
        "compendium.lint.engine",
        "rumps",
        "keyring.backends.macOS",
        "watchdog.observers",
        "watchdog.observers.fsevents",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "tkinter", "test", "unittest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Compendium",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # AC 2: No terminal window
    target_arch=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="Compendium",
)

app = BUNDLE(
    coll,
    name="Compendium.app",
    bundle_identifier="com.compendium.menubar",
    info_plist={
        "CFBundleName": "Compendium",
        "CFBundleDisplayName": "Compendium",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "LSUIElement": False,  # Visible in Dock + menu bar
        "LSMinimumSystemVersion": "13.0",
        "NSSupportsAutomaticTermination": False,
        "NSSupportsSuddenTermination": False,
        "NSDocumentsFolderUsageDescription": (
            "Compendium needs access to read raw sources and write wiki articles."
        ),
        "NSDesktopFolderUsageDescription": (
            "Compendium needs access to read files you drop for ingestion."
        ),
        "NSDownloadsFolderUsageDescription": (
            "Compendium needs access to ingest PDFs and source files."
        ),
    },
)
