"""Runs the guarded cv-agent pipeline for the API and classifies the result.

A produced CV is emitted by cv_presenter_agent as the final event; a
guardrail refusal (bad file, injection, no files) is relayed by the root
agent cv_agent_app. The final event's author tells them apart."""

from dataclasses import dataclass

PRESENTER_AUTHOR = "cv_presenter_agent"


@dataclass
class PipelineResult:
    cv: str | None
    error: str | None


def classify(final_author: str, final_text: str) -> PipelineResult:
    if final_author == PRESENTER_AUTHOR:
        return PipelineResult(cv=final_text, error=None)
    return PipelineResult(cv=None, error=final_text)
