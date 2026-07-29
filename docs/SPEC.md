# CV Agent — Application Specification

Complete specification of the app for anyone (human or agent) picking it up fresh.
Last updated: 2026-07-29.

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
| Observability | Langfuse v3 (self-hosted, Docker) + `openinference-instrumentation-google-adk` |
| Evals | ADK evalsets + pytest (`AgentEvaluator`), plus a custom integration test |

## 3. Architecture

### 3.1 Agent tree

```
cv_agent_app (LlmAgent, model gemini-2.5-flash)          cv_agents/agent.py
│  tools: list_uploaded_files, load_customer_documents   cv_agents/tools.py
│  instruction: cv_agents/prompt.py (ROOT_INSTRUCTION + GLOBAL_INSTRUCTION)
│  output_key: final_cv
└─ cv_writer_sequential_agent (SequentialAgent)          cv_agents/sub_agents/writer/agent.py
   ├─ writer_agent (LlmAgent)      output_key: cv_draft
   └─ reviser_loop_agent (LoopAgent, max_iterations=3)
      ├─ critic_agent (LlmAgent)   output_key: cv_criticism, tool: exit_loop
      └─ reviser_agent (LlmAgent)  output_key: cv_draft   (overwrites!)
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
5. The final revision is the reply; root's `output_key` stores it as `final_cv`.

### 3.3 Data flow — session state contract

Documents and drafts move through **session state**, injected into prompts via
ADK `{placeholder}` templating (strict: missing key ⇒ runtime error, by design):

| State key | Written by | Read by (via templating) |
|---|---|---|
| `customer_cv` | `load_customer_documents` (tool_context.state) | writer, critic, reviser |
| `job_description` | `load_customer_documents` | writer, critic, reviser |
| `cv_draft` | writer_agent AND reviser_agent (output_key) | critic, reviser |
| `cv_criticism` | critic_agent (output_key) | reviser |
| `final_cv` | root agent (output_key) | — |

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
- Known gap: the final CV is never persisted anywhere (no output artifact, no
  file). `tools.save_generated_file` exists but is unused. See §7.

## 4. Configuration

`.env` (gitignored; template in `.env.example`):

```
GOOGLE_GENAI_USE_VERTEXAI=1
GOOGLE_CLOUD_PROJECT=...          # Vertex AI project
GOOGLE_CLOUD_LOCATION=europe-west4
LANGFUSE_PUBLIC_KEY=pk-lf-...     # local Langfuse project keys
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=http://localhost:3000
```

`Config.setup_environment()` exports these for google-genai and Langfuse; call
it before creating clients/instrumentation. Auth is gcloud ADC
(`gcloud auth application-default login`).

## 5. Observability (Langfuse)

- Self-hosted Langfuse v3 at `http://localhost:3000`; Docker compose project in
  the sibling directory `../langfuse` (postgres, clickhouse, redis, minio,
  web, worker).
- **ClickHouse version pin**: `../langfuse/docker-compose.override.yml` pins
  ClickHouse to the version that wrote the data volume. NEVER downgrade
  ClickHouse (e.g. by pulling upstream compose changes): an older server
  detaches newer-format parts as `broken-on-start` and all traces appear lost.
  Recovery: run the newer image, strip the `broken-on-start_` prefix on
  detached part dirs, `ALTER TABLE ... ATTACH PART`.
- Instrumentation is `GoogleADKInstrumentor().instrument()`; the Langfuse
  client (`get_client()`) MUST be initialized before agents run — it registers
  the OTel exporter; spans emitted before that are silently dropped.
- Who traces what:
  - `main.py` → app runs, user `user_1`, session `session_<timestamp>`
  - `tests/eval/conftest.py` → eval runs, user `test_user`, sessions
    `___eval___session___<uuid>` (distinguishable in the UI by User ID)
- Trace anatomy: `invocation` → `agent_run [name]` → `call_llm` / tool spans.
  Tool results return to the model as `function_response` messages — visible in
  the NEXT `call_llm`'s input. Workflow-agent spans never have own `call_llm`s.

## 6. Evaluation

Two complementary layers (see also `docs/superpowers/specs/2026-07-16-adk-trajectory-eval-design.md`):

### 6.1 ADK evalset — `eval/cv_agent.evalset.json`

Criteria (`eval/test_config.json`): `tool_trajectory_avg_score: 1.0` (exact
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
eval/cv_agent.evalset.json --config_file_path eval/test_config.json`) but
writes result files to `cv_agents/.adk/eval_history/` (gitignored); the chosen
workflow is pytest + Langfuse traces as the single record.

## 7. Known gaps / next steps (agreed but not built)

1. **Persist the final CV** — wire `save_generated_file` (or equivalent) so the
   improved CV lands as an artifact/file the user can retrieve.
2. **ADK eval scores → Langfuse score objects** — attach
   `tool_trajectory_avg_score` / `response_match_score` to the eval run's trace
   via `langfuse.create_score()` so judgments live next to traces.
3. **Langfuse LLM-as-a-judge** — online scoring of CV quality (tailoring to
   job spec, no invented experience) on every trace; configured in Langfuse UI.
4. **User-simulation evals** — ADK `ConversationScenario` (persona +
   conversation_plan) for multi-turn robustness; experimental in ADK 1.17.
5. Consider making `max_iterations` and models configurable via `Config`.

## 8. Conventions

- British English in all agent-facing prose and generated CVs.
- Commit style: imperative subject + bulleted body; NO Claude co-author
  trailer. Author identity: `Zak Croft <1917622+zakcroft@users.noreply.github.com>`.
- Never `git push` and never delete files unless the owner explicitly asks.
- `black`/`ruff` line length 100 (pyproject.toml).
