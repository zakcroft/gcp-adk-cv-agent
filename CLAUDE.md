# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Read `docs/SPEC.md` first** — it is the full specification of the app (architecture, data flow, eval strategy, observability stack, known constraints) and is the fastest way to pick this project up from scratch.

## Commands

```bash
uv run main.py                                # run the interactive chat app (type 'exit' to quit)
uv run pytest tests/eval/test_trajectory.py   # ADK evalset (trajectory + response match)
uv run pytest tests/eval/test_improve_cv_flow.py  # happy-path integration test (full pipeline)
uv run adk web                                # ADK dev UI (browser) — root_agent is exposed by cv_agents
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
   └─ reviser_loop_agent (LoopAgent, max_iterations=3)
      ├─ critic_agent (critiques; calls exit_loop to approve/terminate)
      └─ reviser_agent (applies feedback)
```

**Data flows through session state, never through hope:** `load_customer_documents` writes `customer_cv` and `job_description` into state; sub-agent instructions inject them via `{placeholder}` templating (strict — missing key raises). The writer saves its output to state key `cv_draft` (via `output_key`); the reviser **also** writes to `cv_draft` so each loop iteration critiques the latest revision; the critic reads it and writes `cv_criticism`. Do not break this producer→consumer chain — the historical bug here was the root agent transferring to the workflow before loading documents, which turned a "please upload your CV" reply into the draft.

Tools return `.model_dump()` dicts (not Pydantic objects) so Langfuse tool spans render real payloads instead of `<not serializable>`.

## Observability & evals

- Every run is traced to a **local Langfuse** (Docker, `http://localhost:3000`; compose project lives in `../langfuse`). Instrumentation: `GoogleADKInstrumentor` in `main.py` (app runs, user `user_1`) and `tests/eval/conftest.py` (eval runs, user `test_user`, sessions prefixed `___eval___session___`). The Langfuse client must be initialized **before** agents run or spans are dropped.
- ADK evals live in `eval/cv_agent.evalset.json` (cases) + `eval/test_config.json` (criteria: `tool_trajectory_avg_score` 1.0, `response_match_score` 0.5). The eval harness **cannot preload artifacts**, so file-dependent happy paths are covered by `tests/eval/test_improve_cv_flow.py` instead.
- Debugging agent behaviour: query traces via Langfuse REST API (keys in `.env`) or ClickHouse directly (`docker exec langfuse-clickhouse-1 clickhouse-client`).

## Gotchas

- Prompt/agent edits require restarting the running chat process; instructions are loaded at import time.
- The Langfuse stack pins ClickHouse via `../langfuse/docker-compose.override.yml` — do **not** let upstream compose changes downgrade ClickHouse below the version that wrote the data volume (a downgrade detaches all data parts as "broken" and Langfuse appears to lose all traces; they are recoverable by re-attaching, see SPEC).
- This is a personal project (github.com/zakcroft). Never `git push` or delete files unless explicitly asked.
