"""Unit tests for the presenter agent: the deterministic final step of the
CV workflow. It must emit state's cv_draft verbatim (no LLM call) and save it
as a downloadable artifact, so every run ends with the CV regardless of how
the reviser loop exited (critic exit_loop approval vs max_iterations).
"""

from types import SimpleNamespace

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


@pytest.mark.asyncio
async def test_saves_cv_as_artifact():
    ctx = await _make_context({"cv_draft": FINAL_CV})

    async for _ in cv_presenter_agent.run_async(ctx):
        pass

    saved = await ctx.artifact_service.load_artifact(
        app_name="cv_agent_app",
        user_id="u1",
        session_id="s1",
        filename=CV_ARTIFACT_FILENAME,
    )
    assert saved is not None
    assert saved.inline_data.data.decode("utf-8") == FINAL_CV


@pytest.mark.asyncio
async def test_missing_cv_draft_yields_explanatory_message_without_artifact():
    ctx = await _make_context({})

    events = [event async for event in cv_presenter_agent.run_async(ctx)]

    assert len(events) == 1
    assert "no cv" in events[0].content.parts[0].text.lower()
    saved = await ctx.artifact_service.load_artifact(
        app_name="cv_agent_app", user_id="u1", session_id="s1", filename=CV_ARTIFACT_FILENAME
    )
    assert saved is None


def test_presenter_is_last_step_of_workflow():
    from cv_agents.sub_agents.writer.agent import cv_writer_sequential_agent

    assert cv_writer_sequential_agent.sub_agents[-1].name == "cv_presenter_agent"


def test_root_agent_has_no_misleading_final_cv_output_key():
    from cv_agents.agent import root_agent

    assert root_agent.output_key is None


class _FakeSpan:
    def __init__(self, recording=True):
        self.attributes = {}
        self._recording = recording

    def is_recording(self):
        return self._recording

    def set_attribute(self, key, value):
        self.attributes[key] = value


@pytest.mark.asyncio
async def test_judge_metadata_attached_when_state_present(monkeypatch):
    from cv_agents.sub_agents.presenter import agent as presenter_module

    span = _FakeSpan()
    monkeypatch.setattr(
        presenter_module, "otel_trace", SimpleNamespace(get_current_span=lambda: span)
    )
    ctx = await _make_context(
        {"cv_draft": FINAL_CV, "customer_cv": "source cv text", "job_description": "jd text"}
    )

    [event async for event in cv_presenter_agent.run_async(ctx)]

    assert span.attributes["langfuse.observation.metadata.customer_cv"] == "source cv text"
    assert span.attributes["langfuse.observation.metadata.job_description"] == "jd text"


@pytest.mark.asyncio
async def test_judge_metadata_graceful_when_state_absent(monkeypatch):
    from cv_agents.sub_agents.presenter import agent as presenter_module

    span = _FakeSpan()
    monkeypatch.setattr(
        presenter_module, "otel_trace", SimpleNamespace(get_current_span=lambda: span)
    )
    ctx = await _make_context({"cv_draft": FINAL_CV})

    events = [event async for event in cv_presenter_agent.run_async(ctx)]

    assert span.attributes == {}
    assert events[0].content.parts[0].text == FINAL_CV
