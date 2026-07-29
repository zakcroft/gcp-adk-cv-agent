# ADK Trajectory & Response Evaluation — Design

**Date:** 2026-07-16
**Goal:** Add Google ADK evaluation to cv-agent covering both (1) trajectory/tool-use and (2) final-response quality, runnable via the `adk eval` CLI and pytest, as a way to learn the ADK evaluation API.

## Background

- Installed: google-adk 1.17.0 (supports evalsets, criteria config, CLI + `AgentEvaluator`).
- The root agent (`cv_agents/agent.py`) has tools `load_customer_documents` and `list_uploaded_files`, and delegates to `cv_writer_agent`.
- Constraint: the eval harness creates its own runner with an **empty artifact store**, so `load_customer_documents` hits its "no files" path. Eval cases must expect that reality.

## Components

### 1. `eval/cv_agent.evalset.json`
Pydantic-schema evalset with one simple eval case to start ("one of each": one tool-trajectory check + one final-response check):

- **`list_files`** — user asks "What files have I uploaded?"
  - Expected trajectory: one call to `list_uploaded_files` (no args).
  - Expected final response: states no files are uploaded.

The case includes `session_input` (`app_name`, `user_id`, empty state). More cases (e.g. `improve_cv`) can be appended to the same evalset later.

### 2. `eval/test_config.json`
```json
{
  "criteria": {
    "tool_trajectory_avg_score": 1.0,
    "response_match_score": 0.5
  }
}
```
- Trajectory is strict (1.0 = exact tool match).
- Response threshold loose (0.5) because error-path wording varies; can later switch to `final_response_match_v2` (LLM judge) if brittle.

### 3. `tests/eval/test_trajectory.py`
Pytest wrapper using `AgentEvaluator.evaluate(agent_module="cv_agents", eval_dataset_file_path_or_dir="eval/cv_agent.evalset.json")` with `@pytest.mark.asyncio`. Criteria for this path come from a `test_config.json` co-located with the eval data.

### 4. Dependencies
Add `pytest-asyncio` to `[project.optional-dependencies] dev`.

## How to run

```bash
uv run adk eval cv_agents eval/cv_agent.evalset.json \
  --config_file_path eval/test_config.json --print_detailed_results

uv run pytest tests/eval/
```

Both call the real Gemini model on Vertex AI (costs tokens, needs gcloud ADC auth).

## Non-goals (for now)

- Happy-path eval with sample CV/job description preloaded as artifacts (needs fixture/session plumbing — a follow-up).
- Evaluating the writer/critic/reviser loop internals.

## Success criteria

- `adk eval` runs both cases and reports per-criterion pass/fail.
- `pytest tests/eval/` passes when the agent takes the expected trajectory.
