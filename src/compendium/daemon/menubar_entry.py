"""Standalone entry point for the macOS menu bar app (.app bundle).

This is the script that py2app bundles. It auto-discovers the project
directory, runs first-time setup if needed, and launches the menu bar
with the daemon engine.

AC 2: Zero terminal UI — no console windows, only menu bar icon.
AC 3: Permissions — uses NSOpenPanel for explicit folder access grant.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

_PREFS_PATH = Path.home() / ".compendium-app.json"

logger = logging.getLogger("compendium.app")

_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "gemini": "gemini-2.0-flash",
    "ollama": "llama3",
}


def _load_prefs() -> dict:
    """Load app preferences (project_dir, etc.)."""
    if _PREFS_PATH.exists():
        try:
            return json.loads(_PREFS_PATH.read_text())
        except Exception:
            pass
    return {}


def _save_prefs(prefs: dict) -> None:
    """Save app preferences."""
    _PREFS_PATH.write_text(json.dumps(prefs, indent=2))


def _find_project_dir() -> Path | None:
    """Find the Compendium project directory.

    Search order:
    1. Saved preference from previous launch
    2. COMPENDIUM_PROJECT_DIR environment variable
    3. ~/compendium/ if it has a compendium.toml
    """
    import os

    prefs = _load_prefs()
    saved = prefs.get("project_dir")
    if saved:
        p = Path(saved)
        if (p / "compendium.toml").exists():
            return p

    env = os.environ.get("COMPENDIUM_PROJECT_DIR")
    if env:
        p = Path(env)
        if (p / "compendium.toml").exists():
            return p

    home = Path.home() / "compendium"
    if (home / "compendium.toml").exists():
        return home

    return None


def _ask_for_folder() -> Path | None:
    """Show a native macOS folder picker dialog.

    This triggers the macOS file access permission prompt (AC 3).
    Returns the selected path or None if cancelled.
    """
    try:
        from AppKit import NSOpenPanel  # pyobjc
    except ImportError:
        # Fallback: use rumps window to ask for a path string
        import rumps

        response = rumps.Window(
            title="Compendium Setup",
            message=(
                "Welcome! Enter the path to your Obsidian vault\n"
                "(or leave empty for ~/compendium):"
            ),
            ok="OK",
            cancel="Quit",
            dimensions=(400, 24),
            default_text=str(Path.home() / "compendium"),
        ).run()
        if not response.clicked:
            return None
        text = response.text.strip()
        return Path(text) if text else Path.home() / "compendium"

    panel = NSOpenPanel.openPanel()
    panel.setCanChooseDirectories_(True)
    panel.setCanChooseFiles_(False)
    panel.setAllowsMultipleSelection_(False)
    panel.setCanCreateDirectories_(True)
    panel.setTitle_("Choose Your Compendium Vault")
    panel.setMessage_(
        "Select the folder where Compendium will store your knowledge base "
        "(raw/, wiki/, output/). This can be an existing Obsidian vault."
    )
    panel.setPrompt_("Use This Folder")

    result = panel.runModal()
    if result == 1:  # NSModalResponseOK
        url = panel.URLs()[0]
        return Path(url.path())
    return None


def _bring_to_front() -> None:
    """Bring the app to the foreground so dialogs are visible."""
    try:
        from AppKit import NSApplication

        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except ImportError:
        pass


def _first_run_setup() -> Path | None:
    """Run first-time setup: ask user to pick a vault folder."""
    import rumps

    _bring_to_front()
    rumps.alert(
        title="Welcome to Compendium",
        message=(
            "Compendium is an AI-powered knowledge compiler that lives in your menu bar.\n\n"
            "First, choose the folder for your knowledge vault.\n"
            "This is where your raw sources, compiled wiki, and outputs will live."
        ),
        ok="Choose Folder",
    )

    chosen = _ask_for_folder()
    if chosen is None:
        return None

    # Save preference
    _save_prefs({"project_dir": str(chosen)})
    return chosen


def apply_engine_choice(
    config_path: Path,
    provider: str,
    model: str | None = None,
    endpoint: str | None = None,
    api_key: str | None = None,
) -> None:
    """Apply user's engine choice to compendium.toml and Keychain.

    Pure function — no UI. Testable directly.
    """
    from compendium.core.config import CompendiumConfig, ModelConfig

    config = CompendiumConfig.load(config_path)
    resolved_model = model or _DEFAULT_MODELS.get(provider, "")

    mc = ModelConfig(provider=provider, model=resolved_model, endpoint=endpoint)
    config.models.default_provider = provider
    config.models.compilation = mc
    config.models.qa = ModelConfig(provider=provider, model=resolved_model, endpoint=endpoint)
    config.models.lint = ModelConfig(provider=provider, model=resolved_model, endpoint=endpoint)

    if provider == "ollama":
        config.daemon.cloud_only = False

    config.save(config_path)

    if api_key and provider != "ollama":
        from compendium.llm.factory import set_api_key

        set_api_key(provider, api_key)


def _engine_choice_setup(project_dir: Path) -> None:
    """Ask user to choose LLM engine during first-run setup."""
    import rumps

    _bring_to_front()

    # Step 1: Cloud vs Local
    choice = rumps.alert(
        title="Choose Your AI Engine",
        message=(
            "How do you want to power Compendium?\n\n"
            "Cloud API — uses Anthropic, OpenAI, or Gemini (requires API key)\n"
            "Local — uses Ollama running on your Mac (no API key needed)"
        ),
        ok="Cloud API",
        cancel="Local (Ollama)",
    )

    config_path = project_dir / "compendium.toml"

    if choice == 1:  # Cloud API
        # Step 2: Which cloud provider
        resp = rumps.Window(
            title="Cloud Provider",
            message="Which provider?\n\nType: anthropic, openai, or gemini",
            ok="Next",
            cancel="Skip (configure later)",
            dimensions=(300, 24),
            default_text="anthropic",
        ).run()

        if not resp.clicked:
            return

        provider = resp.text.strip().lower()
        if provider not in ("anthropic", "openai", "gemini"):
            provider = "anthropic"

        # Step 3: API key
        key_resp = rumps.Window(
            title=f"API Key: {provider.title()}",
            message=f"Paste your {provider.title()} API key:",
            ok="Save",
            cancel="Skip",
            dimensions=(400, 24),
        ).run()

        api_key = key_resp.text.strip() if key_resp.clicked else None
        apply_engine_choice(config_path, provider, api_key=api_key)

        if api_key:
            rumps.notification(
                "Compendium",
                f"{provider.title()} configured",
                "API key saved to macOS Keychain.",
            )
    else:  # Local / Ollama
        from compendium.llm.ollama import list_ollama_models

        models = list_ollama_models()

        if models:
            model_list = "\n".join(f"  \u2022 {m}" for m in models)
            resp = rumps.Window(
                title="Ollama \u2014 Select Model",
                message=f"Detected models:\n{model_list}\n\nType the model name:",
                ok="Save",
                cancel="Use default",
                dimensions=(350, 24),
                default_text=models[0],
            ).run()
        else:
            rumps.alert(
                title="Ollama Not Detected",
                message=(
                    "Could not connect to Ollama.\n\n"
                    "Please ensure the Ollama app is running, "
                    "then try again from Settings."
                ),
                ok="Continue",
            )
            resp = rumps.Window(
                title="Ollama Model (Manual)",
                message="Enter your Ollama model name:",
                ok="Save",
                cancel="Use default",
                dimensions=(300, 24),
                default_text="llama3",
            ).run()

        model_name = resp.text.strip() if resp.clicked and resp.text.strip() else "llama3"
        apply_engine_choice(
            config_path,
            "ollama",
            model=model_name,
            endpoint="http://localhost:11434",
        )
        rumps.notification(
            "Compendium",
            "Ollama configured",
            f"Using model: {model_name}",
        )


def _offer_login_item() -> None:
    """Offer to add Compendium to macOS Login Items (AC 4)."""
    import rumps

    response = rumps.alert(
        title="Start at Login?",
        message=(
            "Would you like Compendium to start automatically when you log in?\n\n"
            "You can change this later in System Settings > General > Login Items."
        ),
        ok="Yes, start at login",
        cancel="No thanks",
    )
    if response == 1:  # OK clicked
        _register_login_item()


def _register_login_item() -> None:
    """Register the app as a Login Item using macOS SMAppService or launchd."""
    import subprocess

    # Method 1: Try using the current app bundle path with osascript
    # This is the most compatible approach for .app bundles
    app_path = _get_app_bundle_path()
    if app_path:
        try:
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'tell application "System Events" to make login item at end '
                    f'with properties {{path:"{app_path}", hidden:true}}',
                ],
                capture_output=True,
                check=True,
            )
            return
        except subprocess.CalledProcessError:
            pass

    # Method 2: Fall back to launchd plist
    try:
        from compendium.daemon.service import install

        prefs = _load_prefs()
        project_dir = Path(prefs.get("project_dir", str(Path.home() / "compendium")))
        install(project_dir)
    except Exception as exc:
        logger.warning("Could not register login item: %s", exc)


def _get_app_bundle_path() -> str | None:
    """Get the .app bundle path if running inside one."""
    import sys

    # When running as a py2app bundle, sys.executable is inside the .app
    exe = Path(sys.executable)
    for parent in exe.parents:
        if parent.suffix == ".app":
            return str(parent)
    return None


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(Path.home() / ".compendium-app.log"),
            logging.StreamHandler(),
        ],
    )

    try:
        _run_app()
    except Exception as exc:
        logger.exception("Startup error")
        try:
            import rumps

            _bring_to_front()
            rumps.alert(
                title="Compendium \u2014 Startup Error",
                message=f"Failed to load Compendium:\n\n{exc}",
                ok="Quit",
            )
        except Exception:
            pass


def _run_app() -> None:
    """Core app logic, separated so main() can catch and display errors."""
    from compendium.core.config import CompendiumConfig
    from compendium.core.wiki_fs import WikiFileSystem
    from compendium.daemon.engine import DaemonEngine
    from compendium.daemon.menubar import run_menubar

    project_dir = _find_project_dir()

    # First-run setup if no project found
    is_first_run = project_dir is None
    if is_first_run:
        project_dir = _first_run_setup()
        if project_dir is None:
            return  # User cancelled

    # Initialize project if it doesn't exist yet (must happen before engine choice)
    wfs = WikiFileSystem(project_dir)
    if not (project_dir / "compendium.toml").exists():
        wfs.init_project(name="My Knowledge Wiki")

    # First-run: ask engine choice, then offer Login Items
    if is_first_run:
        _engine_choice_setup(project_dir)
        _offer_login_item()

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
