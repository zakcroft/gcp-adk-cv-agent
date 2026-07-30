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

        yield self._text_event(ctx, cv_draft)

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
