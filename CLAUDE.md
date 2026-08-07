# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Read `SPEC.md` first** — it is the full specification of the app (architecture, data flow, eval strategy, observability stack, known constraints) and is the fastest way to pick this project up from scratch.

## Commands

```bash
uv run main.py                                # run the interactive chat app (type 'exit' to quit)
uv run pytest tests/eval/test_trajectory.py   # ADK evalset (trajectory + response match)
uv run pytest tests/eval/test_improve_cv_flow.py  # happy-path integration test (full pipeline)
uv run adk web                                # ADK dev UI (browser) — root_agent is exposed by cv_agents
uv run python scripts/run_dataset_experiment.py [dataset] [run-name]  # regression run over Langfuse dataset + correctness judge
uv run python -m api.app                       # serve the HTTP API on :8000 (job model over the guarded Runner)
./start                                        # full stack: API (:8000) + Vite frontend (:5173); Ctrl-C stops both
```

- Run the two eval test files **separately**, not as one `pytest tests/eval/` run: together they burst ~12 Gemini calls and trip Vertex AI 429 quota. A 429 is quota, not a bug — re-run after a minute.
- `adk eval` CLI needs `PYTHONPATH=$PWD` (it imports the package by file path); pytest gets this via `pythonpath` in pyproject.toml.
- Requires gcloud ADC auth (`gcloud auth application-default login`); project/location come from `.env` (see `.env.example`).

## Architecture

Multi-agent CV improvement pipeline on Google ADK (Gemini via Vertex AI):

```
cv_agent_app (root LlmAgent — tools: list_uploaded_files, load_customer_documents)
└─ cv_writer_sequential_agent (SequentialAgent)
   ├─ writer_agent (drafts the CV)
   ├─ reviser_loop_agent (LoopAgent, max_iterations=3)
   │  ├─ critic_agent (critiques; calls exit_loop to approve/terminate)
   │  └─ reviser_agent (applies feedback)
   └─ cv_presenter_agent (custom BaseAgent, no LLM — emits final cv_draft
      verbatim as the run's last event; saves artifact improved_cv.md)
```

**Data flows through session state, never through hope:** `load_customer_documents` writes `customer_cv` and `job_description` into state; sub-agent instructions inject them via `{placeholder}` templating (strict — missing key raises). The writer saves its output to state key `cv_draft` (via `output_key`); the reviser **also** writes to `cv_draft` so each loop iteration critiques the latest revision; the critic reads it and writes `cv_criticism`. Do not break this producer→consumer chain — the historical bug here was the root agent transferring to the workflow before loading documents, which turned a "please upload your CV" reply into the draft.

Tools return `.model_dump()` dicts (not Pydantic objects) so Langfuse tool spans render real payloads instead of `<not serializable>`.

**Web layer:** `cv_agents/run_pipeline.run_once` is the shared "run the guarded pipeline once" helper (used by the API and experiment runner). `api/` is a FastAPI job-model service over that Runner (PDF in/out via `api/documents.py`); `frontend/` is a React/Vite SPA. `./start` runs both. Full detail in SPEC 3.5.

## Observability & evals

- Every run is traced to a **local Langfuse** (Docker, `http://localhost:3000`; compose project lives in `../langfuse`). Instrumentation: `GoogleADKInstrumentor` in `main.py` (app runs, user `user_1`) and `tests/eval/conftest.py` (eval runs, user `test_user`, sessions prefixed `___eval___session___`). The Langfuse client must be initialized **before** agents run or spans are dropped.
- ADK evals live in `tests/eval/data/cv_agent.evalset.json` (cases) + `tests/eval/data/test_config.json` (criteria: `tool_trajectory_avg_score` 1.0, `response_match_score` 0.5). The eval harness **cannot preload artifacts**, so file-dependent happy paths are covered by `tests/eval/test_improve_cv_flow.py` instead.
- Debugging agent behaviour: query traces via Langfuse REST API (keys in `.env`) or ClickHouse directly (`docker exec langfuse-clickhouse-1 clickhouse-client`).

## Gotchas

- Prompt/agent edits require restarting the running chat process; instructions are loaded at import time.
- The Langfuse instance (v4, clean-installed 2026-07-31) is disposable-and-reproducible: `../langfuse/.env` reseeds the same org/project/API keys on an empty DB (`docker compose down -v && up -d`); evaluators must be recreated in the UI (config snapshot in SPEC section 7, item 3). The override file only mounts Vertex ADC credentials + a ClickHouse compat setting — no version pins remain.
- This is a personal project (github.com/zakcroft). Never `git push` or delete files unless explicitly asked.
