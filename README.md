# CV Agent — AI-Powered CV Improvement System

A multi-agent system on **Google ADK** that rewrites a CV to fit a target job
description **without inventing anything** — the hard part, and the reason
most of this repo is evaluation, guardrails, and observability rather than
prompt-wrangling.

Upload a CV and a job description (PDF or text); a pipeline of specialised
agents drafts, critiques, verifies, and revises an improved CV in British
English, then serves it back as a downloadable PDF.

## What this demonstrates

| Area | Built with |
|---|---|
| Multi-agent orchestration | Google ADK — Sequential + Loop workflows, a custom no-LLM agent |
| LLM | Gemini 2.5 Flash via Vertex AI |
| Truthfulness engineering | in-loop verifier truth gate + a deterministic grounding gate |
| Guardrails | input validation, Model Armor injection screening, output gates, a runtime plugin |
| Evaluation | ADK evalsets, dataset experiments, six LLM-judge scorers, regression cases |
| Observability | Langfuse v4 (self-hosted), OpenTelemetry/OpenInference tracing |
| Prompt management | Langfuse Prompt Management, versioned, composable, drift-tested |
| API | FastAPI job-model service over the guarded pipeline |
| Frontend | React 19 + Vite + TypeScript SPA |
| Tooling | `uv`, pytest, vitest, Docker |

## Framework

Google **ADK** (Agent Development Kit) on Python 3.13, run with `uv`. Gemini
2.5 Flash through **Vertex AI**. Every run is traced to a self-hosted
Langfuse. Prompts for the sub-agents and the judges live in Langfuse Prompt
Management with local fallbacks.

## Workflows

The pipeline composes three ADK workflow primitives:

- **SequentialAgent** — drives writer → reviser-loop → presenter in order.
- **LoopAgent** — the reviser loop (critic → verifier → reviser), capped at
  3 iterations; the verifier ends it early via an `exit_loop` tool.
- **Custom `BaseAgent`** — a deterministic presenter (no LLM) that emits the
  final CV verbatim so the run always ends with the document, not a tool call.

## Agents

| Agent | Role |
|---|---|
| `cv_agent_app` (root) | loads the uploaded documents, then hands off to the pipeline |
| `writer` | drafts the tailored CV from the source CV + JD |
| `critic` | critiques the draft (advisory only) |
| `verifier` | the **truth gate** — checks the draft against the source CV on four rules (faithfulness, hallucination, completeness, misrepresentation) and holds the only `exit_loop` key, so tailoring pressure can never approve an untruthful draft |
| `reviser` | applies critic + verifier feedback |
| `presenter` | deterministic final step; emits and saves the CV |

Data flows through **session state**, injected into prompts by strict
templating — never left to conversation-history luck.

## Guardrails

Layered checks that block or repair at runtime, in a top-level `guardrails/`
package (pure functions, no framework imports):

- **Input** (`inputs.py`) — readable (PDF or UTF-8 text), sane size,
  two-distinct-files, an LLM plausibility check ("is this actually a CV?"),
  and **Model Armor** prompt-injection/jailbreak screening. Fail-open on
  service outage; every agent prompt also carries a data-is-not-instructions
  rule as a second line of defence.
- **Output** (`outputs.py`) — a deterministic **grounding gate** that diffs
  the draft's technologies and proper terms against the source (code the
  model cannot argue with), plus a format check.
- **Runtime** (`runtime.py`) — an ADK **plugin** enforcing a per-run
  LLM-call ceiling and a per-call timeout, registered on the same Runner the
  API and CLI use.

## Observability & tracing

- **Langfuse v4**, self-hosted via Docker; ADK runs instrumented with
  OpenInference so every agent, tool, and model call is a span.
- Trace anatomy mirrors the agent tree (`invocation → agent_run → call_llm`),
  making the multi-agent flow and each guardrail decision inspectable.
- The presenter attaches the source documents to its span as metadata so
  live LLM-judge evaluators can score against them.

## Evaluation

Truthfulness is not a "vibe check" — it is measured, repeatably:

- **ADK evalsets** — tool-trajectory and response-match tests (e.g. the
  load-before-transfer contract).
- **Dataset experiments** — the real pipeline run over a `regression-cases`
  library (well-matched, mismatched, sparse, over-qualified, and
  guardrail-attacking cases), scored and diffed run-over-run in Langfuse.
- **Six LLM judges** — correctness, faithfulness, hallucination,
  completeness, misrepresentation, tailoring — versioned in Prompt
  Management, each with a calibrated worked example.
- **Prompt drift tests** — assert the local prompt fallbacks match the
  versioned Langfuse prompts (which use composability to share a common
  security rule).

## Tests

| Type | What it covers |
|---|---|
| Unit (pytest) | pure guardrail logic, the job store, the CV-vs-refusal classifier, document conversion |
| Guardrail unit | service-backed checks with the Google clients faked — verdict mapping, cost ordering, fail-open |
| Integration (pytest) | the full pipeline end-to-end (quota-gated) |
| ADK eval | tool trajectory + response match |
| Frontend (vitest + Testing Library) | upload → poll → display, download, rerun guard |

## API

A thin **FastAPI** service (`api/`) wrapping the *same* guarded Runner the
CLI uses — never ADK's built-in server, which would bypass the guardrails.
A **job model** decouples the 2–3 minute run from the HTTP request:

- `POST /jobs` — upload CV + JD (PDF or text) → `{ job_id }`; PDFs are
  extracted to text at the boundary.
- `GET /jobs/{id}` — poll status (`running` / `done` / `failed`); a
  guardrail refusal surfaces as a `failed` job with a human reason.
- `GET /jobs/{id}/cv.pdf` — the finished CV as a PDF.

## Frontend

A **React 19 + Vite + TypeScript** SPA (`frontend/`): upload two files, a
polling spinner while the pipeline runs, the improved CV rendered as a paper
sheet, then download (PDF) or rerun (with a download-first guard). Styled as
a deliberate editorial identity, not a templated form.

## Run it

```bash
uv sync                       # Python deps
./start                       # full stack: API on :8000, frontend on :5173
# or individually:
uv run main.py                # interactive CLI
uv run python -m api.app      # API only
```

Requires gcloud ADC auth and a `.env` (see `.env.example`); a local Langfuse
via Docker for tracing. See `SPEC.md` for the full architecture, data-flow
contract, and eval strategy.
