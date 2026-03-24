from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import chainlit as cl

from dialectical_framework.agents.orchestrator.orchestrator import Orchestrator
from dialectical_framework.dialectical_reasoning import DialecticalReasoning
from dialectical_framework.settings import Settings


_APP_READY = False


def _ensure_app_initialized() -> None:
    """Initialize DI and app wiring once before any Chainlit session starts."""
    global _APP_READY
    if _APP_READY:
        return

    DialecticalReasoning.setup(Settings.from_env())
    _APP_READY = True


@cl.on_chat_start
async def on_chat_start():
    _ensure_app_initialized()
    orchestrator = Orchestrator()
    cl.user_session.set("orchestrator", orchestrator)
    await cl.Message(content=f"Session started: {orchestrator.sid}").send()


@cl.on_message
async def on_message(message: cl.Message):
    orchestrator = cl.user_session.get("orchestrator")
    response = await orchestrator.chat(message.content)
    await cl.Message(content=response).send()

def main() -> None:
    """Launch the Chainlit UI for this module."""
    module_path = Path(__file__).resolve()
    project_root = module_path.parents[3]

    env = os.environ.copy()
    env.setdefault("CHAINLIT_HOST", "127.0.0.1")
    env.setdefault("CHAINLIT_PORT", "8000")

    cmd = [
        sys.executable,
        "-m",
        "chainlit",
        "run",
        str(module_path),
        "--host",
        env["CHAINLIT_HOST"],
        "--port",
        env["CHAINLIT_PORT"],
    ]

    subprocess.run(cmd, cwd=project_root, env=env, check=True)


if __name__ == "__main__":
    main()