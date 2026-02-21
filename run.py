"""
run.py - Start the LiveKit voice server (loads agent from transformation_layer).

  uv run python run.py

One-time setup first: uv run python scripts/setup.py
Requires .env: LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, OPENAI_API_KEY
Test: uv run python scripts/join_room.py my-room
"""

import json
import logging
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env", override=True)
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

# Import plugins on the main thread so they register before workers spawn
from livekit.plugins import silero, noise_cancellation, openai as _openai_plugin  # noqa: F401
from livekit.plugins.turn_detector import english as _td  # noqa: F401

WORKFLOW_PATH = Path(__file__).parent / "sample_workflow.json"
_ENV_WORKFLOW_PATH = "RUN_PY_WORKFLOW_PATH"


def load_workflow(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)

async def _rtc_entrypoint(ctx):
    from livekit.agents import room_io

    # Ensure workflow_parser loggers are visible in worker process
    logging.getLogger("workflow_parser").setLevel(logging.INFO)
    logger.info("Agent job started for room=%s", ctx.room.name)

    path = os.environ.get(_ENV_WORKFLOW_PATH)
    if not path:
        raise RuntimeError("RUN_PY_WORKFLOW_PATH not set")
    workflow = load_workflow(Path(path))
    ctx.log_context_fields = {"room": ctx.room.name}

    from workflow_parser.transformation_layer import build_agents_from_workflow
    logger.info("Building agent from transformation_layer...")
    agent, session = await build_agents_from_workflow(workflow, ctx)
    if agent is None:
        raise RuntimeError("build_agents_from_workflow returned agent=None; implement transformation_layer")
    if session is None:
        raise RuntimeError("build_agents_from_workflow returned session=None; implement transformation_layer to return (Agent, AgentSession)")

    await session.start(
        agent=agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=noise_cancellation.BVC(),
            ),
        ),
    )


def _prewarm(proc):
    proc.userdata["vad"] = silero.VAD.load()


def main():
    sys.argv = [sys.argv[0], "dev"]  # LiveKit CLI expects a command (dev = run worker)

    workflow_path = WORKFLOW_PATH.resolve()
    if not workflow_path.exists():
        logger.error("Workflow not found: %s", workflow_path)
        sys.exit(1)
    os.environ[_ENV_WORKFLOW_PATH] = str(workflow_path)

    from livekit.agents import AgentServer, cli
    server = AgentServer()
    server.setup_fnc = _prewarm
    server.rtc_session(agent_name="voice-agent")(_rtc_entrypoint)

    print("\n" + "=" * 50)
    print("Voice agent running (from transformation_layer)")
    print("Test: uv run python scripts/join_room.py my-room")
    print("=" * 50 + "\n")
    cli.run_app(server)


if __name__ == "__main__":
    main()
