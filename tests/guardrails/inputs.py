import pytest
from google.adk.agents.invocation_context import InvocationContext
from google.adk.artifacts import InMemoryArtifactService
from google.adk.sessions import InMemorySessionService

from cv_agents.sub_agents.presenter.agent import CV_ARTIFACT_FILENAME, cv_presenter_agent

FINAL_CV = "John Smith\nSenior Backend Engineer\n\nPROFESSIONAL SUMMARY\nExample."


async def _make_context(state: dict) -> InvocationContext:
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="cv_agent_app", user_id="u1", session_id="s1", state=state
    )
    return InvocationContext(
        session_service=session_service,
        artifact_service=InMemoryArtifactService(),
        invocation_id="inv-1",
        agent=cv_presenter_agent,
        session=session,
    )



@pytest.mark.asyncio
async def test_emits_cv_draft_verbatim():
    ctx = await _make_context({"cv_draft": FINAL_CV})

    events = [event async for event in cv_presenter_agent.run_async(ctx)]

    assert len(events) == 1
    assert events[0].author == "cv_presenter_agent"
    assert events[0].content.parts[0].text == FINAL_CV