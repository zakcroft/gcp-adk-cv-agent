"""Runs the guarded cv-agent pipeline for the API and classifies the result.

The run itself is the shared cv_agents.run_pipeline.run_once helper; this
module only adds the API's interpretation of the outcome: a produced CV is
emitted by cv_presenter_agent as the final event, whereas a guardrail
refusal (bad file, injection, no files) is relayed by the root agent
cv_agent_app. The final event's author tells them apart."""

from dataclasses import dataclass

from cv_agents.run_pipeline import run_once

_ARTIFACTS = ("sample_cv.txt", "sample_job_description.txt")
_IMPROVE_MESSAGE = "Please improve my CV for this job description."

PRESENTER_AUTHOR = "cv_presenter_agent"


@dataclass
class PipelineResult:
    cv: str | None
    error: str | None


def classify(final_author: str, final_text: str) -> PipelineResult:
    if final_author == PRESENTER_AUTHOR:
        return PipelineResult(cv=final_text, error=None)
    return PipelineResult(cv=None, error=final_text)


async def run_cv_pipeline(cv_bytes: bytes, jd_bytes: bytes) -> PipelineResult:
    artifacts = list(zip(_ARTIFACTS, (cv_bytes, jd_bytes)))
    final_author, final_text = await run_once(artifacts, _IMPROVE_MESSAGE, user_id="api_user")
    return classify(final_author, final_text)
