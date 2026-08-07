"""Run the multi-agent pipeline once over a set of uploaded documents.

Single source of truth for the "fresh guarded session → load artifacts →
run → capture the final event" block that the API and the experiment runner
both need. (main.py does not use this: its interactive chat loop keeps a
persistent session and streams turns, which this one-shot helper does not.)
"""

import uuid

from cv_agents.config import Config

# setup_environment must run before root_agent is imported (it configures
# Vertex + Langfuse env vars the agent construction reads). Idempotent, so
# callers that also call it are harmless.
_config = Config()
_config.setup_environment()

from google.adk.artifacts import InMemoryArtifactService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from cv_agents.agent import root_agent
from cv_agents.debug_plugin import maybe_debug_plugins
from guardrails.runtime import GuardrailsPlugin


async def run_once(
    artifacts: list[tuple[str, bytes]], message: str, user_id: str = "pipeline_user"
) -> tuple[str, str]:
    """One full pipeline run in a fresh guarded session.

    Returns (final_author, final_text): the author distinguishes a produced
    CV (cv_presenter_agent) from a relayed refusal (cv_agent_app). user_id
    is passed through for Langfuse trace attribution."""
    session_id = f"run_{uuid.uuid4().hex[:8]}"
    session_service = InMemorySessionService()
    artifact_service = InMemoryArtifactService()
    await session_service.create_session(
        app_name=_config.app_name, user_id=user_id, session_id=session_id
    )
    for filename, data in artifacts:
        await artifact_service.save_artifact(
            app_name=_config.app_name,
            user_id=user_id,
            session_id=session_id,
            filename=filename,
            artifact=types.Part.from_bytes(data=data, mime_type="text/plain"),
        )

    runner = Runner(
        agent=root_agent,
        app_name=_config.app_name,
        artifact_service=artifact_service,
        session_service=session_service,
        plugins=[GuardrailsPlugin(), *maybe_debug_plugins()],
    )

    final_author, final_text = "", ""
    new_message = types.Content(role="user", parts=[types.Part(text=message)])
    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=new_message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            if event.content.parts[0].text:
                final_author = event.author
                final_text = event.content.parts[0].text
    return final_author, final_text
