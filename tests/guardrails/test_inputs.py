"""Unit tests for the input guardrail chain.

The deterministic checks are tested directly. The service-backed checks
(plausibility, injection screening) are tested with the Google clients
replaced by fakes — these tests cover OUR wrapper logic (verdict mapping,
the service-down path), not the services themselves. Real API behaviour is
covered by tests/eval/test_improve_cv_flow.py and the eval cases.
"""

from types import SimpleNamespace

import pytest
from google.cloud import modelarmor_v1

import guardrails.inputs as inputs
from guardrails.inputs import (
    PlausibilityVerdict,
    check_duplicates,
    check_inputs,
    check_readable,
    check_size,
)

# Comfortably inside the 200–50,000 character window.
CV_TEXT = "x" * 300
JD_TEXT = "y" * 300


# --- deterministic checks: plain functions, plain tests ---------------------


def test_readable_accepts_plain_utf8_text():
    assert check_readable(b"hello cv", "text/plain") is True


def test_readable_rejects_wrong_mime_type():
    assert check_readable(b"%PDF-1.4", "application/pdf") is False


def test_readable_rejects_bytes_that_are_not_utf8():
    assert check_readable(b"\xff\xfe\x00junk", "text/plain") is False


def test_size_accepts_documents_in_range():
    assert check_size(CV_TEXT, JD_TEXT) is True


def test_size_rejects_too_short_and_too_long():
    assert check_size("tiny", JD_TEXT) is False
    assert check_size(CV_TEXT, "y" * 60_000) is False


def test_size_rejects_whitespace_only():
    assert check_size(" " * 300, JD_TEXT) is False


def test_duplicates_rejects_identical_content():
    assert check_duplicates(CV_TEXT, CV_TEXT) is False
    assert check_duplicates(CV_TEXT, JD_TEXT) is True


# --- fakes for the service-backed checks ------------------------------------


class FakeGenAIClient:
    """Stands in for genai.Client: returns a fixed verdict, or raises."""

    def __init__(self, verdict=None, error=None):
        async def generate_content(**kwargs):
            if error is not None:
                raise error
            return SimpleNamespace(parsed=verdict)

        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))


class FakeArmorClient:
    """Stands in for ModelArmorAsyncClient: fixed match state, or raises."""

    def __init__(self, match_state=None, error=None):
        self._match_state = match_state
        self._error = error

    async def sanitize_user_prompt(self, request):
        if self._error is not None:
            raise self._error
        return SimpleNamespace(
            sanitization_result=SimpleNamespace(filter_match_state=self._match_state)
        )


def wire_fakes(monkeypatch, genai_client, armor_client):
    """Point inputs.py at the fakes instead of the real Google clients."""
    monkeypatch.setattr(inputs.genai, "Client", lambda: genai_client)
    monkeypatch.setattr(
        inputs.modelarmor_v1, "ModelArmorAsyncClient", lambda **kwargs: armor_client
    )


BOTH_OK = PlausibilityVerdict(cv_ok=True, jd_ok=True, reason="")
NO_MATCH = modelarmor_v1.FilterMatchState.NO_MATCH_FOUND
MATCH = modelarmor_v1.FilterMatchState.MATCH_FOUND


# --- the chain end to end, with fakes ---------------------------------------


@pytest.mark.asyncio
async def test_chain_passes_good_documents(monkeypatch):
    wire_fakes(monkeypatch, FakeGenAIClient(BOTH_OK), FakeArmorClient(NO_MATCH))

    verdict = await check_inputs(CV_TEXT.encode(), "text/plain", JD_TEXT.encode(), "text/plain")

    assert verdict.ok is True


@pytest.mark.asyncio
async def test_chain_stops_at_deterministic_failure_without_calling_services(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("service client built for an input that failed the free tier")

    monkeypatch.setattr(inputs.genai, "Client", explode)
    monkeypatch.setattr(inputs.modelarmor_v1, "ModelArmorAsyncClient", explode)

    verdict = await check_inputs(b"%PDF-1.4", "application/pdf", JD_TEXT.encode(), "text/plain")

    assert verdict.ok is False
    assert "plain text" in verdict.reason


@pytest.mark.asyncio
async def test_plausibility_rejection_reason_reaches_the_caller(monkeypatch):
    not_a_cv = PlausibilityVerdict(cv_ok=False, jd_ok=True, reason="Document A is a shopping list.")
    wire_fakes(monkeypatch, FakeGenAIClient(not_a_cv), FakeArmorClient(NO_MATCH))

    verdict = await check_inputs(CV_TEXT.encode(), "text/plain", JD_TEXT.encode(), "text/plain")

    assert verdict.ok is False
    assert verdict.reason == "Document A is a shopping list."


@pytest.mark.asyncio
async def test_injection_match_rejects_the_upload(monkeypatch):
    wire_fakes(monkeypatch, FakeGenAIClient(BOTH_OK), FakeArmorClient(MATCH))

    verdict = await check_inputs(CV_TEXT.encode(), "text/plain", JD_TEXT.encode(), "text/plain")

    assert verdict.ok is False
    assert "manipulate" in verdict.reason


@pytest.mark.asyncio
async def test_broken_services_let_the_upload_continue(monkeypatch):
    """The choice we made on purpose: if a checking service is down, log
    and continue rather than turn every user away."""
    boom = ConnectionError("service unavailable")
    wire_fakes(monkeypatch, FakeGenAIClient(error=boom), FakeArmorClient(error=boom))

    verdict = await check_inputs(CV_TEXT.encode(), "text/plain", JD_TEXT.encode(), "text/plain")

    assert verdict.ok is True
