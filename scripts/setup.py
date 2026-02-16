#!/usr/bin/env python3
"""
One-time setup: check dependencies and download turn-detector models.

Run from project root:
  uv run python scripts/setup.py

Or after uv sync:
  python scripts/setup.py
"""

import sys
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent.parent


def check_dependencies():
    """Verify required packages are installed. Return True if all ok."""
    required = [
        ("dotenv", "python-dotenv"),
        ("livekit.agents", "livekit-agents"),
        ("livekit.plugins.silero", "livekit-plugins-silero (livekit-agents)"),
        ("livekit.plugins.turn_detector.english", "livekit-plugins-turn-detector (livekit-agents)"),
        ("livekit.plugins.noise_cancellation", "livekit-plugins-noise-cancellation"),
        ("livekit.api", "livekit-api"),
    ]
    missing = []
    for module, label in required:
        try:
            __import__(module)
        except ImportError as e:
            missing.append((label, str(e)))
    if missing:
        print("Missing or broken dependencies:")
        for label, err in missing:
            print(f"  - {label}: {err}")
        print("\nInstall with:  uv sync")
        return False
    print("Dependencies OK")
    return True


def download_files():
    """Download turn-detector models (English) from Hugging Face."""
    print("Downloading turn-detector models...")
    try:
        import livekit.plugins.turn_detector.english  # noqa: F401 - registers plugin
        from livekit.agents import Plugin
        for plugin in Plugin.registered_plugins:
            plugin.download_files()
        print("Turn-detector models OK")
        return True
    except Exception as e:
        print(f"Download failed: {e}")
        return False


def main():
    print("Setup: dependencies + turn-detector models\n")
    if not check_dependencies():
        sys.exit(1)
    if not download_files():
        sys.exit(1)
    print("\nSetup complete. Next: uv run python run.py")


if __name__ == "__main__":
    main()
