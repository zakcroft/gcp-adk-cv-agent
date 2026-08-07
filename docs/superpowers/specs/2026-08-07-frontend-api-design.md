# Frontend + API — Design

**Date:** 2026-08-07 · **Status:** agreed in discussion, pending review
**Scope:** a web UI and HTTP API for the cv-agent pipeline. Spec covers the
full product vision; **only Phase 1 is built now**.

## 1. Problem

The pipeline runs only from `main.py` (a CLI loop). To use it from a
browser we need an HTTP API and a UI. The API must drive the **same**
`Runner` the CLI uses so the guardrails stay in the loop — ADK's built-in
`adk web` / `adk api_server` builds its own Runner **without**
`GuardrailsPlugin`, so it is not an option.

## 2. Product vision (north star)

The end-state, so the phased build does not paint into corners:

- Pipeline runs, returns to the **root agent**, which hands off to a new
  **editor agent** — the human-in-the-loop surface.
- The UI shows the CV plus an **analysis panel** built from the judges'
  findings. Clicking a finding highlights the **exact span** in the CV.
- The user edits by talking to a **highlighted span** ("tone this down") or
  the **whole document** ("make it more concise"); the editor agent applies
  the change.

**Load-bearing consequence:** click-to-highlight requires every finding to
carry the exact offending text, not just a score and prose reason. The
verifier already emits `evidence` (exact quote) and the grounding gate
emits flagged terms; the four eval judges (faithfulness, hallucination,
completeness, tailoring) currently emit only `{score, reason}` and must be
upgraded to return the span. This also ties the judges — today pure
observability — into the product.

## 3. Phased roadmap

| Phase | Delivers |
|---|---|
| **1 (now)** | One-shot: upload CV + JD → job → poll → CV → download + rerun. No analysis, no editing, no versioning. |
| 2 | SSE progress on the same job model; read-only analysis panel with click-to-highlight (judges emit spans). |
| 3 | Editor agent + conversational editing (per-span and whole-doc); route back through root; presenter phase 2; draft versioning. |

Each phase is a separate spec → plan → build cycle. This document details
Phase 1; Phases 2–3 are captured only as vision above.

## 4. Architecture

```
React + Vite SPA  ──HTTP──▶  FastAPI service  ──▶  Runner(plugins=[GuardrailsPlugin()])
   (static)                   (job store)            = the same pipeline main.py drives
```

- **API is a thin wrapper** around the existing `root_agent` + `Runner`.
  It owns HTTP, file upload, and job state; it adds no agent logic.
- **The Runner is ours**, with `GuardrailsPlugin` — never `adk web`.
- **Job model** decouples the 2–3 min run from the HTTP request: proxies
  and serverless kill long-held connections, so the run happens in a
  background task and the client polls. (SSE progress is Phase 2, layered
  on the same job model — not a replacement for it.)

New code lives in a top-level `api/` package; the FE in a top-level `web/`.
Neither touches `cv_agents/` internals beyond importing `root_agent` and
the guardrails, mirroring how `scripts/run_dataset_experiment.py` already
constructs a Runner.

## 5. API contract (Phase 1)

| Method | Path | Body / Params | Returns |
|---|---|---|---|
| POST | `/jobs` | multipart: `cv` file, `jd` file | `{ "job_id": str }` (202) |
| GET | `/jobs/{id}` | — | `{ "status": "running\|done\|failed", "error": str? }` |
| GET | `/jobs/{id}/cv` | — | CV text (`text/markdown`); 409 if not `done` |

- `POST /jobs` saves the two uploads as artifacts under the names the tools
  expect (`sample_cv.txt`, `sample_job_description.txt`), creates a session,
  starts the pipeline as a background task, and returns a job id at once.
- A **guardrail rejection** (unreadable file, wrong size, duplicate,
  not-a-CV, injection) surfaces as `status: "failed"` with the
  guardrail's user-facing `error` — the pipeline already returns this from
  `load_customer_documents`; the API relays it.
- Rerun is just another `POST /jobs` → new job id. No server-side link
  between runs in Phase 1.

## 6. Job model & state

- A `Job` holds `id`, `status`, `cv` (result text), `error`, `created_at`.
- **Phase 1 store: in-memory dict**, single process — matches the
  in-memory session/artifact services already used everywhere. A restart
  loses jobs; acceptable for local/single-user.
- Productionization swaps the dict for Redis or a DB (Section 9) with no
  API-contract change.
- Background execution: FastAPI `BackgroundTasks` (or an `asyncio` task)
  runs the pipeline and writes the result/error back into the job.

## 7. Phase-1 frontend

React + Vite + TypeScript SPA. A separate Node server is unnecessary — the
API is Python, so the FE is a static build talking to it over HTTP.

Screens (one page):
- Two file inputs (CV, JD) + Submit.
- Spinner while polling `GET /jobs/{id}` every ~3 s.
- On `done`: render the CV in a display area; **Download** and **Rerun**.
- On `failed`: show the guardrail/error message and let the user re-pick
  files.

Rules:
- **Download-before-rerun:** if the current draft has not been downloaded,
  Rerun warns before discarding it (versioning is deferred, so the guard
  prevents silent loss).
- No routing, no auth, no state library — `useState` and `fetch` suffice.

## 8. Error handling

| Case | Surfaces as |
|---|---|
| Guardrail rejection | job `failed` + the guardrail `error` string |
| Pipeline exception | job `failed` + a generic message; details logged/Langfuse |
| Poll for unknown job | 404 |
| Download before done | 409 |
| Run exceeds call ceiling / times out | `CallCeilingExceeded` / timeout → job `failed` (runtime guardrail already covers this) |

## 9. Productionization (noted now, built later)

Not in Phase 1; recorded so Phase 1 does not block them:

- **Auth** — none locally; required before public exposure (API key or
  OAuth). CORS locked to the FE origin.
- **Deploy** — FastAPI on Cloud Run (region `europe-west4`, matching
  Vertex + Model Armor); FE as a static bundle (Cloud Storage + CDN or
  similar). Cloud Run request timeout is fine because the job runs in the
  background, not in the request.
- **Job store** — Redis or a DB, replacing the in-memory dict, so jobs
  survive restarts and scale past one instance.
- **Rate limiting** — protect the Vertex quota; the runtime call-ceiling
  guardrail is per-run, not per-user.
- **PII pseudonymisation** — SPEC item 10 becomes relevant once real users
  upload real CVs (redact before external calls, restore on output).
- **Secrets** — already `.env` + gcloud ADC; move to Secret Manager on
  Cloud Run.

## 10. Testing

- **API:** pytest with FastAPI `TestClient`. Fake the pipeline (patch
  `root_agent`/Runner) so API tests are fast and quota-free: assert job
  lifecycle (`POST` → `running` → `done`/`failed`), guardrail rejection →
  `failed` + reason, download gating (409 before done, 404 unknown).
- **One integration test** exercises a real pipeline run through the API
  end-to-end (quota-gated, like `test_improve_cv_flow.py`).
- **FE:** component test of the upload→poll→display flow with the API
  mocked; a manual/chrome pass on the real UI.

## 11. Out of scope (Phase 1)

Analysis panel, click-to-highlight, editor agent, conversational editing,
presenter phase 2, draft versioning, SSE progress, auth, multi-user, the
judge-span upgrade. All are Phase 2–3 (Section 3).
