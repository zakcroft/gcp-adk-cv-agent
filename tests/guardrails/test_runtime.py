"""Unit tests for the runtime guardrails plugin: the per-run call ceiling
and the per-call timeout stamp. Contexts and requests are stand-ins with
the same shape; no model is ever called."""

from types import SimpleNamespace

import pytest

from guardrails.runtime import (
    MAX_LLM_CALLS_PER_RUN,
    PER_CALL_TIMEOUT_MS,
    CallCeilingExceeded,
    GuardrailsPlugin,
)


def _request():
    return SimpleNamespace(config=None)


async def _call(plugin, invocation_id="run-1", request=None):
    return await plugin.before_model_callback(
        callback_context=SimpleNamespace(invocation_id=invocation_id),
        llm_request=request if request is not None else _request(),
    )


@pytest.mark.asyncio
async def test_stamps_timeout_on_every_request():
    plugin = GuardrailsPlugin()
    request = _request()

    result = await _call(plugin, request=request)

    assert result is None  # the model call itself must proceed
    assert request.config.http_options.timeout == PER_CALL_TIMEOUT_MS


@pytest.mark.asyncio
async def test_does_not_override_an_existing_timeout():
    from google.genai import types

    plugin = GuardrailsPlugin()
    request = SimpleNamespace(
        config=types.GenerateContentConfig(http_options=types.HttpOptions(timeout=5))
    )

    await _call(plugin, request=request)

    assert request.config.http_options.timeout == 5


@pytest.mark.asyncio
async def test_ceiling_stops_a_runaway_run():
    plugin = GuardrailsPlugin()
    for _ in range(MAX_LLM_CALLS_PER_RUN):
        await _call(plugin)

    with pytest.raises(CallCeilingExceeded):
        await _call(plugin)


@pytest.mark.asyncio
async def test_runs_are_counted_separately():
    plugin = GuardrailsPlugin()
    for _ in range(MAX_LLM_CALLS_PER_RUN):
        await _call(plugin, invocation_id="run-1")

    # a different run still has its full allowance
    assert await _call(plugin, invocation_id="run-2") is None


@pytest.mark.asyncio
async def test_finished_runs_are_forgotten():
    plugin = GuardrailsPlugin()
    for _ in range(MAX_LLM_CALLS_PER_RUN):
        await _call(plugin)

    await plugin.after_run_callback(
        invocation_context=SimpleNamespace(invocation_id="run-1")
    )

    assert plugin._calls_by_invocation == {}
    assert await _call(plugin) is None  # counter restarted
