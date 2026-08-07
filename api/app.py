"""FastAPI surface for the cv-agent pipeline (Phase 1: job model).

POST two files -> job id; poll GET /jobs/{id}; fetch the CV when done.
The pipeline runs as a background task so the 2-3 min run never blocks the
request. Wraps the SAME guarded Runner as the CLI — see api/pipeline.py."""

import asyncio
import logging

from fastapi import FastAPI, HTTPException, Response, UploadFile
from fastapi.responses import PlainTextResponse

from api.documents import render_pdf, to_text_bytes
from api.jobs import JobStore
from api.pipeline import run_cv_pipeline
from cv_agents.observability import init_langfuse

logger = logging.getLogger(__name__)

# Wire ADK->Langfuse tracing before any job runs, so prod runs are traced and
# the live evaluators fire. Without this the API path runs blind (see
# cv_agents/observability.py). Returned client is used to flush per job below.
_langfuse = init_langfuse()

app = FastAPI(title="cv-agent")
store = JobStore()

# Vertex quota (429) is transient — retry with growing backoff before giving
# up, so a busy-moment burst self-heals instead of failing the job. The job
# model already tolerates the extra wait (the client just keeps polling).
_RETRY_DELAYS = (10, 30, 60, 120)


async def _run(job_id: str, cv_bytes: bytes, jd_bytes: bytes) -> None:
    try:
        for attempt, delay in enumerate((*_RETRY_DELAYS, None)):
            try:
                result = await run_cv_pipeline(cv_bytes, jd_bytes)
                break
            except Exception as e:  # pipeline blew up (not a guardrail refusal)
                is_quota = "429" in str(e)
                if is_quota and delay is not None:
                    logger.warning(
                        "429 on job %s (attempt %d); retrying in %ss", job_id, attempt + 1, delay
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.exception("Pipeline run failed for job %s", job_id)
                detail = (
                    "Too many requests right now — please wait a minute and try again."
                    if is_quota
                    else "The pipeline failed. Please try again."
                )
                store.mark_failed(job_id, detail)
                return

        if result.cv is not None:
            store.mark_done(job_id, result.cv)
        else:
            store.mark_failed(job_id, result.error or "Unknown error.")
    finally:
        # Short-lived job: force the OTel batch exporter to ship this run's
        # spans now, so the trace and its live evaluators aren't lost if the
        # process idles before the next batch flush.
        _langfuse.flush()


@app.post("/jobs", status_code=202)
async def create_job(cv: UploadFile, jd: UploadFile) -> dict:
    # Normalise PDFs to text at the boundary so the pipeline (and its
    # guardrails) always see plain text.
    cv_bytes = to_text_bytes(await cv.read())
    jd_bytes = to_text_bytes(await jd.read())
    job = store.create()
    asyncio.create_task(_run(job.id, cv_bytes, jd_bytes))
    return {"job_id": job.id}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    return {"status": job.status, "error": job.error}


def _ready_cv(job_id: str) -> str:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    if job.status != "done" or job.cv is None:
        raise HTTPException(status_code=409, detail="CV not ready")
    return job.cv


@app.get("/jobs/{job_id}/cv")
def get_cv(job_id: str) -> Response:
    return PlainTextResponse(_ready_cv(job_id), media_type="text/markdown")


@app.get("/jobs/{job_id}/cv.pdf")
def get_cv_pdf(job_id: str) -> Response:
    pdf = render_pdf(_ready_cv(job_id))
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="improved_cv.pdf"'},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
