#!/usr/bin/env python3
"""
Print a LiveKit Meet URL with token so you can join a room and talk to the agent.
Loads LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET from .env (project root).

Usage (from project root):
  uv run python scripts/join_room.py [ROOM_NAME]
  uv run python scripts/join_room.py test-room
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

# Project root = parent of scripts/
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
os.chdir(root)

try:
    from dotenv import load_dotenv
    load_dotenv(root / ".env", override=True)  # .env wins over shell/env
except ImportError:
    pass

def main():
    room = (sys.argv[1] if len(sys.argv) > 1 else "test-room").strip()
    url = os.environ.get("LIVEKIT_URL", "").strip()
    api_key = os.environ.get("LIVEKIT_API_KEY", "").strip()
    api_secret = os.environ.get("LIVEKIT_API_SECRET", "").strip()

    if not all((url, api_key, api_secret)):
        print("Missing env: set LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET (e.g. in .env)", file=sys.stderr)
        sys.exit(1)

    try:
        from livekit.api import (
            AccessToken,
            VideoGrants,
            RoomConfiguration,
            RoomAgentDispatch,
        )
    except ImportError:
        print("Install livekit-api: uv sync", file=sys.stderr)
        sys.exit(1)

    grant = VideoGrants(room_join=True, room=room)
    # Dispatch the voice-agent to the room when the participant connects
    room_config = RoomConfiguration(
        agents=[RoomAgentDispatch(agent_name="voice-agent")],
    )
    token = (
        AccessToken(api_key=api_key, api_secret=api_secret)
        .with_grants(grant)
        .with_identity("user")
        .with_name("You")
        .with_ttl(timedelta(hours=1))
        .with_room_config(room_config)
        .to_jwt()
    )

    # LiveKit Meet URL format: https://meet.livekit.io?liveKitUrl=WS_URL&token=TOKEN
    ws_url = url.replace("https://", "wss://").replace("http://", "ws://")
    meet_url = f"https://meet.livekit.io/custom?liveKitUrl={ws_url}&token={token}"
    print(meet_url)

if __name__ == "__main__":
    main()
