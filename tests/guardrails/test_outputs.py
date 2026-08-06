"""Unit tests for the output guardrails, plus the presenter's use of them.

check_grounding's thresholds were calibrated against examples/regression-cases: every
hand-curated expected output must pass clean against its own CV and JD —
that invariant is enforced here so case-library growth keeps the gate
honest.
"""

from pathlib import Path

import pytest

from guardrails.outputs import check_format, check_grounding

CASES = sorted(p for p in Path("examples/regression-cases").iterdir() if p.is_dir())

SOURCE_CV = (
    "John Smith\nSoftware Engineer\n\nEXPERIENCE\n"
    "Built APIs with Python and Django. Worked with PostgreSQL databases.\n"
    "SKILLS\nPython, Django, PostgreSQL, Docker\n"
) * 3  # repeated to clear the format floor in presenter tests
JD = "We are seeking a backend engineer. Requirements: Python, AWS, Kubernetes."


# --- grounding --------------------------------------------------------------


@pytest.mark.parametrize("case_dir", CASES, ids=lambda p: p.name)
def test_every_expected_output_is_clean(case_dir):
    violations = check_grounding(
        (case_dir / "expected_output.md").read_text(),
        (case_dir / "cv.txt").read_text(),
        (case_dir / "jd.txt").read_text(),
    )
    assert violations == []


def test_invented_technology_is_flagged():
    draft = SOURCE_CV + "\nExpert in Terraform and GraphQL."
    assert check_grounding(draft, SOURCE_CV, JD) == ["Terraform", "GraphQL"]


def test_jd_vocabulary_is_allowed():
    draft = SOURCE_CV + "\nKeen to develop Kubernetes and AWS skills."
    assert check_grounding(draft, SOURCE_CV, JD) == []


def test_sentence_case_and_hyphenated_prose_are_not_flagged():
    draft = SOURCE_CV + "\nDelivered results. Strong hands-on problem-solving throughout."
    assert check_grounding(draft, SOURCE_CV, JD) == []


def test_empty_jd_still_works():
    draft = SOURCE_CV + "\nExpert in Terraform."
    assert check_grounding(draft, SOURCE_CV) == ["Terraform"]


# --- format -----------------------------------------------------------------


def test_format_accepts_a_plain_cv():
    assert check_format(SOURCE_CV) == []


def test_format_flags_short_long_and_markdown():
    assert any("too short" in p for p in check_format("hi"))
    assert any("implausibly long" in p for p in check_format("x" * 30_000))
    assert any("markdown" in p for p in check_format(SOURCE_CV + "\n## Section\n**bold**"))


# --- presenter wiring -------------------------------------------------------


async def _run_presenter(state):
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.artifacts import InMemoryArtifactService
    from google.adk.sessions import InMemorySessionService

    from cv_agents.sub_agents.presenter.agent import cv_presenter_agent

    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="cv_agent_app", user_id="u1", session_id="s1", state=state
    )
    ctx = InvocationContext(
        session_service=session_service,
        artifact_service=InMemoryArtifactService(),
        invocation_id="inv-1",
        agent=cv_presenter_agent,
        session=session,
    )
    return [event async for event in cv_presenter_agent.run_async(ctx)]


@pytest.mark.asyncio
async def test_presenter_emits_clean_draft_without_note():
    events = await _run_presenter({"cv_draft": SOURCE_CV, "customer_cv": SOURCE_CV})
    assert events[0].content.parts[0].text == SOURCE_CV


@pytest.mark.asyncio
async def test_presenter_appends_note_for_ungrounded_terms():
    draft = SOURCE_CV + "\nExpert in Terraform."
    events = await _run_presenter(
        {"cv_draft": draft, "customer_cv": SOURCE_CV, "job_description": JD}
    )
    text = events[0].content.parts[0].text
    assert text.startswith(draft)
    assert "Terraform" in text.split("---")[-1]
    assert "verify" in text.split("---")[-1]
