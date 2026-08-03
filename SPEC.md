# CV Agent — Application Specification

Complete specification of the app for anyone (human or agent) picking it up fresh.
Last updated: 2026-08-02.

## 1. Purpose

An AI system that improves a customer's CV to target a specific job description.
The user uploads two text documents (current CV, target job description); a
multi-agent pipeline drafts, critiques, and revises an improved CV in British
English, preserving factual accuracy while tailoring emphasis to the role.

## 2. Tech stack

| Concern | Choice |
|---|---|
| Agent framework | Google ADK (`google-adk[eval]` ≥ 1.17) |
| LLM | Gemini 2.5 Flash via **Vertex AI** (project/location from `.env`) |
| Package/run | `uv` (Python ≥ 3.10; venv at `.venv`) |
| Config | `pydantic-settings` reading `.env` (`cv_agents/config.py`, env prefix `GOOGLE_`, Langfuse keys via `validation_alias`) |
| Observability | Langfuse v4 (self-hosted, Docker) + `openinference-instrumentation-google-adk` |
| Evals | ADK evalsets + pytest (`AgentEvaluator`), plus a custom integration test |

## 3. Architecture

### 3.1 Agent tree

```
cv_agent_app (LlmAgent, model gemini-2.5-flash)          cv_agents/agent.py
│  tools: list_uploaded_files, load_customer_documents   cv_agents/tools.py
│  instruction: cv_agents/prompt.py (ROOT_INSTRUCTION + GLOBAL_INSTRUCTION)
│
│  Writer/critic/reviser instructions are fetched at import from Langfuse
│  Prompt Management (`writer-instruction` / `critic-instruction` /
│  `reviser-instruction`, label `production`; v1 = original, v2 = grounded
│  anti-fabrication, v3 critic/reviser = no JD-vocabulary adoption) via cv_agents/remote_prompts.py, falling back to the
│  local prompt.py text if Langfuse is down. Edit prompts in the UI; restart
│  the app to pick up a new version. The root agent's instruction is local
│  only. When promoting a new production version, re-sync the local
│  prompt.py fallbacks — tests/unit/test_prompt_sync.py fails on drift.
└─ cv_writer_sequential_agent (SequentialAgent)          cv_agents/sub_agents/writer/agent.py
   ├─ writer_agent (LlmAgent)      output_key: cv_draft
   ├─ reviser_loop_agent (LoopAgent, max_iterations=3)
   │  ├─ critic_agent (LlmAgent)   output_key: cv_criticism, tool: exit_loop
   │  └─ reviser_agent (LlmAgent)  output_key: cv_draft   (overwrites!)
   └─ cv_presenter_agent (custom BaseAgent, NO LLM)      cv_agents/sub_agents/presenter/agent.py
      emits state `cv_draft` verbatim as the final event; saves it as
      artifact `improved_cv.md`
```

Naming convention: `_agent` suffix = LLM worker; `_sequential_`/`_loop_` = ADK
workflow containers (no LLM calls of their own). These names are what appear as
`agent_run [...]` spans in Langfuse.

### 3.2 Conversation flow

1. On EVERY user message the root agent calls `list_uploaded_files` first
   (its instruction forbids claiming files are missing without checking).
2. Greeting → reply naming the uploaded files.
3. "Improve my CV" request → root MUST call `load_customer_documents` and see
   `status="success"` BEFORE `transfer_to_agent(cv_writer_sequential_agent)`.
   Files missing → ask the user to upload; do not transfer.
4. `writer_agent` drafts; then the loop runs critic → reviser up to 3 times.
   The critic calls the built-in `exit_loop` tool to approve and terminate
   early (max_iterations is a ceiling, not a quota).
5. `cv_presenter_agent` ends every run by emitting the final `cv_draft`
   verbatim (deterministic, no LLM call) and saving it as artifact
   `improved_cv.md`. Rationale: once the critic gained `exit_loop`, an
   approved run's last event was the exit_loop function response — the
   user-facing reply and the trace's final output stopped being the CV
   (Langfuse LLM-judges scored "generation is empty"). The presenter makes
   the last event the CV regardless of how the loop exits.

### 3.3 Data flow — session state contract

Documents and drafts move through **session state**, injected into prompts via
ADK `{placeholder}` templating (strict: missing key ⇒ runtime error, by design):

| State key | Written by | Read by (via templating) |
|---|---|---|
| `customer_cv` | `load_customer_documents` (tool_context.state) | writer, critic, reviser |
| `job_description` | `load_customer_documents` | writer, critic, reviser |
| `cv_draft` | writer_agent AND reviser_agent (output_key) | critic, reviser |
| `cv_criticism` | critic_agent (output_key) | reviser |

(`final_cv` — a former root-agent `output_key` — was removed: after a
transfer the root never produced the CV, so the key stored chat text under a
misleading name. `cv_draft` is the single source of truth; the presenter
also persists it as the `improved_cv.md` artifact.)

Design rule: **never let critical data depend on conversation-history luck or
LLM discretion.** Prompts must receive data by injection, not describe data
they hope to receive. (Historical bug: root transferred without loading; the
writer's "please upload your CV" plea became `cv_draft` and the loop churned on
garbage for 3 iterations.)

Writer and reviser output PLAIN CV TEXT (no JSON wrappers) so state keys hold
actual content. The critic outputs JSON (`feedback_summary`,
`revision_required`) or calls `exit_loop`.

Tools return `.model_dump()` dicts, not Pydantic models — functionally
identical for ADK, but Langfuse tool spans can serialize dicts (Pydantic
renders as `<not serializable>`).

### 3.4 Files / artifacts

- Inputs live in the ADK **artifact service** (in-memory). `main.py` preloads
  `examples/sample_cv.txt` and `examples/sample_job_description.txt` at startup.
- `InMemorySessionService` + `InMemoryArtifactService`: all state/artifacts are
  lost when the process exits. Each `main.py` run is genuinely a new session
  (`SESSION_ID = session_<timestamp>` so Langfuse groups per run).
- The final CV is persisted by `cv_presenter_agent` as artifact
  `improved_cv.md` (in-memory service, so per-process like everything else).
  `tools.save_generated_file` remains unused.

## 4. Configuration

`.env` (gitignored; template in `.env.example`):

```
GOOGLE_GENAI_USE_VERTEXAI=1
GOOGLE_CLOUD_PROJECT=...          # Vertex AI project
GOOGLE_CLOUD_LOCATION=global   # global routes to available capacity; regional
                               # endpoints (europe-west4) 429 under call bursts
LANGFUSE_PUBLIC_KEY=pk-lf-...     # local Langfuse project keys
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=http://localhost:3000
LANGFUSE_TRACING_ENVIRONMENT="local"  # environment stamped on app traces
```

`Config.setup_environment()` exports these for google-genai and Langfuse; call
it before creating clients/instrumentation. Auth is gcloud ADC
(`gcloud auth application-default login`).

## 5. Observability (Langfuse)

- Self-hosted Langfuse **v4** at `http://localhost:3000`; Docker compose
  project in the sibling directory `../langfuse` (postgres, clickhouse, redis,
  minio, web, worker). Clean-installed 2026-07-31 (v3 volumes wiped; the old
  ClickHouse version pin is gone — upstream's pinned image owns the fresh
  volume, so plain `git pull` + `up -d` is safe again).
- **Instance is reproducible, not precious**: `../langfuse/.env` holds
  `LANGFUSE_INIT_*` vars that reseed the same org/project/**API keys** (matching
  this repo's `.env`) on an empty database — recovery from anything is
  `docker compose down -v && up -d` + recreating evaluators in the UI.
- `../langfuse/docker-compose.override.yml` (local-only) does two jobs: mounts
  gcloud ADC + `GOOGLE_CLOUD_PROJECT` into web AND worker (the
  `google-vertex-ai` LLM connection resolves ADC server-side; judge evals run
  in the worker), and mounts `clickhouse-compat.xml`
  (`query_plan_optimize_lazy_materialization=0`, guards against a ClickHouse
  optimizer bug that 500'd the Scores tab).
- No SMTP is configured: password reset / email change / "forgot password" do
  NOT work — fix accounts via direct `users`-table updates or a reseed.
- Instrumentation is `GoogleADKInstrumentor().instrument()`; the Langfuse
  client (`get_client()`) MUST be initialized before agents run — it registers
  the OTel exporter; spans emitted before that are silently dropped.
- Who traces what:
  - `main.py` → app runs, user `user_1`, session `session_<timestamp>`,
    environment `local` (`LANGFUSE_TRACING_ENVIRONMENT` in `.env`, exported
    by `Config.setup_environment()` via setdefault so the pytest conftest
    wins)
  - ALL pytest runs → environment `pytest` (`tests/conftest.py` sets
    `LANGFUSE_TRACING_ENVIRONMENT` before imports — needed because importing
    cv_agents initialises the Langfuse client for prompt fetching, so even
    unit tests emit traces); eval runs additionally use user `test_user`,
    sessions `___eval___session___<uuid>`
  - experiments → environment `sdk-experiment`, user `experiment_user`
  - Live evaluators filter environment `any of: local` (include, never
    exclude — new/internal environments then cannot leak in).
- Trace anatomy: `invocation` → `agent_run [name]` → `call_llm` / tool spans.
  Tool results return to the model as `function_response` messages — visible in
  the NEXT `call_llm`'s input. Workflow-agent spans never have own `call_llm`s.

## 6. Evaluation

Three complementary layers (see also
`docs/superpowers/specs/2026-07-16-adk-trajectory-eval-design.md` and
`docs/superpowers/specs/2026-07-31-eval-suite-design.md`).

**The two-lane model** (Langfuse side):
- **Lane 1 — regression (code):** `scripts/run_dataset_experiment.py` runs the
  REAL pipeline over Langfuse dataset `regression-cases` (items = input +
  expected expected CV) and scores each item with an in-code LLM judge → score
  `correctness` ("does output match the known-good answer?"). The judge prompt
  is shared via Langfuse Prompt Management: `correctness-judge`, label
  `production`; each score records `judge_prompt_version`. Run:
  `uv run python scripts/run_dataset_experiment.py [dataset] [run-name]` —
  name runs after WHAT CHANGED (like a commit message); runs carry
  `metadata.source=code`. UI "prompt experiments" over the same dataset are
  prompt+model only (cannot run the pipeline) — for prompt play, not testing.
- **Lane 2 — live (UI):** observation evaluator, score `relevance` ("does the
  reply address what was asked?"), managed Relevance template, judge
  `gemini-2.5-flash` via the `google` ADC connection. Filters:
  `Is Root Observation = true` AND environment NOT IN the six internal envs
  (critical: without the env exclusion it mis-judges experiment traces — the
  root span there is the SDK wrapper, not the ADK invocation).

Naming rules (all names are load-bearing — filters/dashboards match on
strings): scores = the question asked (`relevance`, `correctness`); datasets =
purpose (`regression-cases`); prompts = role (`correctness-judge`); run names
= what changed. Traffic sources: `user_1` (chat), `test_user` (pytest),
`experiment_user` (experiments); environments partition automatically
(`default` / `sdk-experiment` / `langfuse-llm-as-a-judge`).

v4 note: an experiment run has no storage of its own — it is `experiment_*`
labels stamped on its traces' events. Deleting a run = deleting its traces
(no UI for this yet; use `DELETE /api/public/traces`).

### 6.1 ADK evalset — `tests/eval/data/cv_agent.evalset.json`

Criteria (`tests/eval/data/test_config.json`): `tool_trajectory_avg_score: 1.0` (exact
tool-call match), `response_match_score: 0.5` (ROUGE similarity; loose because
wording varies).

Cases:
- `list_files` — "What files have I uploaded?" → exactly one
  `list_uploaded_files` call → answer says none uploaded.
- `improve_cv_missing_files` — improve request with NO files → must check the
  list and ask for uploads; must NOT transfer to the workflow.

Constraint: the eval harness starts with an EMPTY artifact store and
`SessionInput` cannot preload artifacts — so evalset cases can only cover
no-files behaviour.

### 6.2 Happy-path integration test — `tests/eval/test_improve_cv_flow.py`

Preloads the example artifacts, sends the improve request, then asserts:
`load_customer_documents` called BEFORE `transfer_to_agent`; state contains
`customer_cv`/`job_description`/`cv_draft`; final response is a substantial
CV, not an error. This is the regression guard for the transfer-before-load bug.

### 6.3 Running & quota

Run the two test files separately (`pytest tests/eval/test_trajectory.py`,
then `pytest tests/eval/test_improve_cv_flow.py`). Together they burst ~12
Gemini calls and hit Vertex AI `429 RESOURCE_EXHAUSTED` on this project's
quota. 429 = quota, not a regression; wait ~1 min and retry.

`adk eval` CLI also works (`PYTHONPATH=$PWD uv run adk eval cv_agents
tests/eval/data/cv_agent.evalset.json --config_file_path tests/eval/data/test_config.json`) but
writes result files to `cv_agents/.adk/eval_history/` (gitignored); the chosen
workflow is pytest + Langfuse traces as the single record.

## 7. Known gaps / next steps (agreed but not built)

1. ~~Persist the final CV~~ — DONE: `cv_presenter_agent` saves
   `improved_cv.md` as an artifact and ends every run with the CV text.
2. **ADK eval scores → Langfuse score objects** — attach
   `tool_trajectory_avg_score` / `response_match_score` to the eval run's trace
   via `langfuse.create_score()` so judgments live next to traces.
3. **Eval suite** — both lanes live (section 6): `relevance` (UI, live) +
   `correctness` (code, experiments). Config snapshot for recreating the UI
   evaluator after a reseed: filter `Is Root Observation = true` + env
   exclusions, 100% sampling, 30s delay, mappings `query` ← Input
   `$.new_message.parts[0].text`, `generation` ← Output
   `$.content.parts[0].text`. NEXT: the four truthfulness judges
   (Faithfulness, Hallucination, Completeness, Job-tailoring) per
   `2026-07-31-eval-suite-design.md` — needs the presenter-metadata spike.
4. **Investigate `correctness` = 0.5** — both scored runs report the same
   regressions vs the expected output CV (job title downgraded, tailoring lost, skills
   disorganised). Determine: real pipeline weakness vs over-fitted single expected output
   item vs run variance. The learning loop: read judge reasons → tweak
   writer/reviser prompts → rerun experiment with a change-named run → compare.
5. **Grow `regression-cases`** — 1 item today (expected output hand-curated 2026-08-01:
   fabrications stripped, titles kept honest — every fact grounded in the
   original CV; expected outputs must pass the same faithfulness bar as the pipeline).
   Claude drafts the new CV/JD pairs + expected outputs; owner reviews. Planned cases:
   - 2–3 CV/JD pairs across industries and seniority levels
   - a sparse CV (little to work with — does the pipeline invent to
     compensate? the fabrication problem as a test case)
   - a mismatched CV/JD pair (does tailoring stay honest?)
   - no-files cases (expected output = the "please upload" reply; reuse
     `cv_agent.evalset.json` wording)
   Prereq for multi-pair items: items must carry/name their own documents and
   the runner must load them per item (today it always loads the sample pair).
6. **Delete junk experiment runs** — `run-20260731_135205/_142919/_143527`
   (429 casualties + unscored first run); v4 has no UI delete, use
   `DELETE /api/public/traces` on their trace ids. Owner go-ahead pending.
7. **User-simulation evals** — ADK `ConversationScenario` (persona +
   conversation_plan) for multi-turn robustness; experimental in ADK 1.17.
8. Consider making `max_iterations` and models configurable via `Config`.
9. **Migrate to ADK 2.x** — see
   `docs/superpowers/specs/2026-07-29-adk-v2-upgrade-assessment.md`:
   recommended two-step 1.17 → 1.36.x now, 2.x once
   `openinference-instrumentation-google-adk` supports it. Both eval lanes are
   the safety net for the migration itself.
10. **Presenter phase 2** — transfer back to root after presenting so the
    user can discuss/iterate the CV; re-target the live evaluator when the
    final event becomes chat again (see presenter design discussion).
11. **ADK eval scores → Langfuse scores** — attach
    `tool_trajectory_avg_score` / `response_match_score` via
    `langfuse.create_score()` so pytest judgments live next to traces.

## 8. Conventions

- **This spec is kept current by a Claude Code Stop hook**
  (`.claude/hooks/spec-reminder.sh`, registered in `.claude/settings.json`):
  when a session ends a turn with changes in `cv_agents/`, `main.py`, or
  `tests/`, the hook prompts the agent once per change-set to reconcile this
  file. Update SPEC.md when changes are meaningful; say so briefly when not.
- British English in all agent-facing prose and generated CVs.
- Commit style: imperative subject + bulleted body; NO Claude co-author
  trailer. Author identity: `Zak Croft <1917622+zakcroft@users.noreply.github.com>`.
- Never `git push` and never delete files unless the owner explicitly asks.
- `black`/`ruff` line length 100 (pyproject.toml).
