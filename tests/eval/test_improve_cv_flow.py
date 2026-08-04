"""Happy-path integration test: improve the CV with documents present.

The ADK eval harness cannot preload artifacts (SessionInput has no artifact
support), so the full pipeline is exercised here instead: load the example
files like main.py does, send the improve request, and assert the trajectory
and the final output.

Regression guard for the transfer-before-load bug: the root agent used to
hand off to the writer without loading the documents, producing an error CV.
"""

from pathlib import Path

import pytest
from google.adk.artifacts import InMemoryArtifactService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from cv_agents.agent import root_agent
from cv_agents.config import Config

PROJECT_ROOT = Path(__file__).parent.parent.parent
config = Config()

USER_ID = "test_user"
SESSION_ID = "eval_improve_cv_flow"


async def _load_example_artifacts(artifact_service):
    case_dir = PROJECT_ROOT / "examples" / "cases" / "senior-match"
    for filename, case_file in (
        ("sample_cv.txt", "cv.txt"),
        ("sample_job_description.txt", "jd.txt"),
    ):
        content = (case_dir / case_file).read_bytes()
        await artifact_service.save_artifact(
            app_name=config.app_name,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=filename,
            artifact=types.Part.from_bytes(data=content, mime_type="text/plain"),
        )


@pytest.mark.asyncio
async def test_improve_cv_happy_path():
    session_service = InMemorySessionService()
    artifact_service = InMemoryArtifactService()
    await session_service.create_session(
        app_name=config.app_name, user_id=USER_ID, session_id=SESSION_ID
    )
    await _load_example_artifacts(artifact_service)

    runner = Runner(
        agent=root_agent,
        app_name=config.app_name,
        artifact_service=artifact_service,
        session_service=session_service,
    )

    msg = types.Content(
        role="user",
        parts=[types.Part(text="Please improve my CV for the job description I provided.")],
    )

    tool_calls = []
    final_text = ""
    async for event in runner.run_async(user_id=USER_ID, session_id=SESSION_ID, new_message=msg):
        for call in event.get_function_calls():
            tool_calls.append(call.name)
        if event.is_final_response() and event.content and event.content.parts:
            if event.content.parts[0].text:
                final_text = event.content.parts[0].text

    # Trajectory: documents must be loaded before handing off to the workflow
    assert "load_customer_documents" in tool_calls, f"tool calls were: {tool_calls}"
    assert "transfer_to_agent" in tool_calls, f"tool calls were: {tool_calls}"
    assert tool_calls.index("load_customer_documents") < tool_calls.index("transfer_to_agent")

    # State: the deterministic data flow populated the draft
    session = await session_service.get_session(
        app_name=config.app_name, user_id=USER_ID, session_id=SESSION_ID
    )
    assert session.state.get("customer_cv"), "customer_cv missing from state"
    assert session.state.get("job_description"), "job_description missing from state"
    assert len(session.state.get("cv_draft", "")) > 500, "cv_draft missing or too short"

    # Output: a real CV, not an error report
    assert len(final_text) > 500, f"final response too short: {final_text[:200]!r}"
    assert "error" not in final_text[:300].lower(), f"final response is an error: {final_text[:300]!r}"
