"""Runs the guarded cv-agent pipeline for the API and classifies the result.

A produced CV is emitted by cv_presenter_agent as the final event; a
guardrail refusal (bad file, injection, no files) is relayed by the root
agent cv_agent_app. The final event's author tells them apart."""

import uuid
from dataclasses import dataclass

from google.adk.artifacts import InMemoryArtifactService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from cv_agents.config import Config
from cv_agents.debug_plugin import maybe_debug_plugins
from cv_agents.agent import root_agent
from guardrails.runtime import GuardrailsPlugin

_config = Config()
_config.setup_environment()

USER_ID = "api_user"
_ARTIFACTS = ("sample_cv.txt", "sample_job_description.txt")
_IMPROVE_MESSAGE = "Please improve my CV for this job description."

PRESENTER_AUTHOR = "cv_presenter_agent"


@dataclass
class PipelineResult:
    cv: str | None
    error: str | None


def classify(final_author: str, final_text: str) -> PipelineResult:
    if final_author == PRESENTER_AUTHOR:
        return PipelineResult(cv=final_text, error=None)
    return PipelineResult(cv=None, error=final_text)


async def run_cv_pipeline(cv_bytes: bytes, jd_bytes: bytes) -> PipelineResult:
    session_id = f"api_{uuid.uuid4().hex[:8]}"
    session_service = InMemorySessionService()
    artifact_service = InMemoryArtifactService()
    await session_service.create_session(
        app_name=_config.app_name, user_id=USER_ID, session_id=session_id
    )
    for filename, data in zip(_ARTIFACTS, (cv_bytes, jd_bytes)):
        await artifact_service.save_artifact(
            app_name=_config.app_name,
            user_id=USER_ID,
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
    message = types.Content(role="user", parts=[types.Part(text=_IMPROVE_MESSAGE)])
    async for event in runner.run_async(
        user_id=USER_ID, session_id=session_id, new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            if event.content.parts[0].text:
                final_author = event.author
                final_text = event.content.parts[0].text
    return classify(final_author, final_text)
