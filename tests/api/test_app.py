import asyncio

import pytest
from fastapi.testclient import TestClient

import api.app as appmod
from api.app import app
from api.pipeline import PipelineResult


@pytest.fixture(autouse=True)
def fresh_store():
    appmod.store = appmod.JobStore()
    yield


def _submit(client):
    return client.post(
        "/jobs",
        files={
            "cv": ("cv.txt", b"cv bytes", "text/plain"),
            "jd": ("jd.txt", b"jd bytes", "text/plain"),
        },
    )


def _wait(client, job_id, want):
    body = None
    for _ in range(50):
        body = client.get(f"/jobs/{job_id}").json()
        if body["status"] == want:
            return body
        asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.01))
    raise AssertionError(f"job never reached {want}: {body}")


def test_job_reaches_done_with_a_cv(monkeypatch):
    async def fake(cv, jd):
        return PipelineResult(cv="IMPROVED CV", error=None)

    monkeypatch.setattr(appmod, "run_cv_pipeline", fake)
    client = TestClient(app)
    r = _submit(client)
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    body = _wait(client, job_id, "done")
    assert body["error"] is None
    assert client.get(f"/jobs/{job_id}/cv").text == "IMPROVED CV"

    pdf = client.get(f"/jobs/{job_id}/cv.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content[:5] == b"%PDF-"


def test_guardrail_refusal_marks_job_failed(monkeypatch):
    async def fake(cv, jd):
        return PipelineResult(cv=None, error="Please upload a real CV.")

    monkeypatch.setattr(appmod, "run_cv_pipeline", fake)
    client = TestClient(app)
    job_id = _submit(client).json()["job_id"]
    body = _wait(client, job_id, "failed")
    assert body["error"] == "Please upload a real CV."


def test_pdf_upload_is_accepted(monkeypatch):
    from api.documents import render_pdf

    seen = {}

    async def fake(cv, jd):
        seen["cv"] = cv
        return PipelineResult(cv="IMPROVED CV", error=None)

    monkeypatch.setattr(appmod, "run_cv_pipeline", fake)
    client = TestClient(app)
    pdf = render_pdf("Owen Prentice\nSoftware Developer\nBuilt Django services.")
    r = client.post(
        "/jobs",
        files={
            "cv": ("cv.pdf", pdf, "application/pdf"),
            "jd": ("jd.txt", b"a plain job description", "text/plain"),
        },
    )
    assert r.status_code == 202
    _wait(client, r.json()["job_id"], "done")
    # the PDF reached the pipeline as extracted text, not raw PDF bytes
    assert b"Owen Prentice" in seen["cv"]
    assert seen["cv"][:5] != b"%PDF-"


def test_unknown_job_is_404():
    assert TestClient(app).get("/jobs/nope").status_code == 404


def test_cv_before_done_is_409(monkeypatch):
    async def never(cv, jd):
        await asyncio.sleep(10)
        return PipelineResult(cv="x", error=None)

    monkeypatch.setattr(appmod, "run_cv_pipeline", never)
    client = TestClient(app)
    job_id = _submit(client).json()["job_id"]
    assert client.get(f"/jobs/{job_id}/cv").status_code == 409
