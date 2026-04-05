#!/bin/bash
# Build Compendium.app — standalone macOS menu bar application.
#
# Usage:
#   ./scripts/build_app.sh
#
# Output:
#   dist/Compendium.app   — the standalone .app bundle
#   dist/Compendium.dmg   — (optional) disk image for distribution
#
# Prerequisites:
#   uv sync --group dev
#   uv pip install py2app

set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Cleaning previous build..."
rm -rf build/ dist/

echo "==> Installing py2app..."
uv pip install py2app 2>/dev/null || true

echo "==> Building Compendium.app..."
uv run python setup_app.py py2app --no-strip

echo "==> Build complete!"
echo "    App bundle: dist/Compendium.app"

# Check if the app was created
if [ -d "dist/Compendium.app" ]; then
    echo "    Size: $(du -sh dist/Compendium.app | cut -f1)"

    # Optional: create DMG for distribution
    if command -v hdiutil &>/dev/null; then
        echo "==> Creating DMG installer..."
        hdiutil create -volname "Compendium" \
            -srcfolder dist/Compendium.app \
            -ov -format UDZO \
            dist/Compendium.dmg 2>/dev/null || true
        if [ -f "dist/Compendium.dmg" ]; then
            echo "    DMG: dist/Compendium.dmg ($(du -sh dist/Compendium.dmg | cut -f1))"
        fi
    fi

    echo ""
    echo "==> To install:"
    echo "    cp -r dist/Compendium.app /Applications/"
    echo ""
    echo "==> To test:"
    echo "    open dist/Compendium.app"
else
    echo "ERROR: Build failed — dist/Compendium.app not found"
    exit 1
fi
