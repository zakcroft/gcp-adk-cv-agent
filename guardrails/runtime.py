"""Runtime guardrails — cross-cutting limits registered once on the Runner
(`Runner(plugins=[GuardrailsPlugin()])`), so they apply to every agent and
model call in the pipeline without any agent knowing they exist.

Unlike inputs/outputs these are not pure functions: the call counter holds
state across a run, so they live in an ADK Plugin. Note: `adk web` builds
its own Runner and does not register this plugin.
"""

import logging
from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins import BasePlugin
from google.genai import types

logger = logging.getLogger(__name__)

# A backstop, not a budget: the pipeline's worst case is ~15 calls (root
# turns + writer + 3 loop iterations of critic/verifier/reviser). Reaching
# 25 means something is genuinely wrong — stop before it burns quota.
MAX_LLM_CALLS_PER_RUN = 25

# A hung connection must raise instead of stalling forever (2026-08-04: a
# dead verifier call stalled a dataset run for over 100 minutes). Generous
# enough for the slowest real call; the client raises when it expires and
# the existing retry/backoff handling takes over.
PER_CALL_TIMEOUT_MS = 120_000


class CallCeilingExceeded(Exception):
    """Raised when a single run tries to make more LLM calls than the
    ceiling allows. Deliberately loud: the run dies visibly rather than
    spending quota on a malfunction."""


class GuardrailsPlugin(BasePlugin):
    """Counts model calls per run and stamps a timeout on every request."""

    def __init__(self) -> None:
        super().__init__(name="guardrails")
        self._calls_by_invocation: dict[str, int] = {}

    async def before_model_callback(
        self, *, callback_context: CallbackContext, llm_request: LlmRequest
    ) -> Optional[LlmResponse]:
        invocation_id = callback_context.invocation_id
        count = self._calls_by_invocation.get(invocation_id, 0) + 1
        self._calls_by_invocation[invocation_id] = count
        if count > MAX_LLM_CALLS_PER_RUN:
            raise CallCeilingExceeded(
                f"run {invocation_id} attempted LLM call {count} "
                f"(ceiling {MAX_LLM_CALLS_PER_RUN})"
            )

        if llm_request.config is None:
            llm_request.config = types.GenerateContentConfig()
        if llm_request.config.http_options is None:
            llm_request.config.http_options = types.HttpOptions()
        if llm_request.config.http_options.timeout is None:
            llm_request.config.http_options.timeout = PER_CALL_TIMEOUT_MS

        return None  # never answers the call itself; the model call proceeds

    async def after_run_callback(self, *, invocation_context: InvocationContext) -> None:
        """A run finished: drop its counter so the dict cannot grow forever."""
        count = self._calls_by_invocation.pop(invocation_context.invocation_id, 0)
        if count:
            logger.info(f"guardrails: run used {count} LLM calls")
