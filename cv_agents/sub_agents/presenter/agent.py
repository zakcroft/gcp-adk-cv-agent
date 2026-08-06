"""Deterministic final step of the CV workflow.

Since the critic gained exit_loop, an approved run's last event was the
exit_loop function response instead of the CV — breaking the user-facing
final reply and any evaluator reading the trace's final output. This agent
makes every run end with the finished CV: no LLM call, so the text is
emitted byte-for-byte from state.
"""

import logging
from typing import AsyncGenerator

from google.adk.agents import BaseAgent, InvocationContext
from google.adk.events import Event
from google.genai import types

from guardrails import check_format, check_grounding

logger = logging.getLogger(__name__)

CV_ARTIFACT_FILENAME = "improved_cv.md"


class CvPresenterAgent(BaseAgent):
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        cv_draft = ctx.session.state.get("cv_draft", "")

        if not cv_draft:
            logger.warning("cv_presenter: no cv_draft in session state")
            yield self._text_event(ctx, "No CV draft was produced by the workflow.")
            return

        # Output guardrails: deterministic checks the loop's LLM verifier
        # cannot be argued out of. Format problems are logged; grounding
        # violations are surfaced to the user under the CV (the artifact
        # stays the pure CV) — the loop is over, so honesty beats silence.
        for problem in check_format(cv_draft):
            logger.warning(f"cv_presenter format check: {problem}")

        note = ""
        customer_cv = ctx.session.state.get("customer_cv", "")
        if customer_cv:
            violations = check_grounding(
                cv_draft, customer_cv, ctx.session.state.get("job_description", "")
            )
            if violations:
                logger.warning(f"cv_presenter grounding violations: {violations}")
                note = (
                    "\n\n---\nPlease verify before using this CV: the following "
                    "terms do not appear in your original CV or the job "
                    "description: " + ", ".join(violations)
                )

        if ctx.artifact_service is not None:
            version = await ctx.artifact_service.save_artifact(
                app_name=ctx.app_name,
                user_id=ctx.user_id,
                session_id=ctx.session.id,
                filename=CV_ARTIFACT_FILENAME,
                artifact=types.Part.from_bytes(
                    data=cv_draft.encode("utf-8"), mime_type="text/markdown"
                ),
            )
            logger.info(f"Saved final CV as '{CV_ARTIFACT_FILENAME}' (version {version})")

        yield self._text_event(ctx, cv_draft + note)

    def _text_event(self, ctx: InvocationContext, text: str) -> Event:
        return Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            content=types.Content(role="model", parts=[types.Part(text=text)]),
        )


cv_presenter_agent = CvPresenterAgent(
    name="cv_presenter_agent",
    description="Presents the final revised CV to the user and saves it as a downloadable artifact.",
)
