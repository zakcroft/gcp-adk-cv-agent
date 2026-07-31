# CV-Agent Eval Suite — Design

**Date:** 2026-07-31 · **Status:** approved design, pending review
**Depends on:** Langfuse v4 (clean install 2026-07-31, `events_only`) · presenter agent (committed, `f46fb12`)

## 1. Goal

Every live run gets judged automatically. One evaluator per failure mode; core risk: the improved CV must be true.

## 2. The suite

| # | Evaluator | Source | Catches | Variables |
|---|---|---|---|---|
| 1 | Faithfulness | RAGAS | Invention — claims not grounded in original CV | output=final CV, context=original CV |
| 2 | Hallucination | Langfuse | Implied embellishment #1's claim-decomposition misses; cross-checks #1 | output=final CV, context=original CV |
| 3 | Completeness | custom | Omission — jobs/skills/projects dropped from original | context=original CV, output=final CV |
| 4 | Job-tailoring | custom | Generic CV that ignores the JD's requirements | output=final CV, context=JD |
| 5 | Relevance | Langfuse | Conversational sanity, all paths (incl. no-files) | query=user msg, output=final answer |

- Excluded: Toxicity/PII — CV is PII by design; cost without signal.
- #3 prompt: list material items in original (jobs, quals, named projects, skill groups); score = fraction retained in rewrite; missing job/degree/project caps at 0.5.
- #4 prompt: extract 5–8 key JD requirements; score = weighted fraction the CV addresses with evidence; no credit for unsupported claims.

## 3. Variable sourcing

- Problem: #1–#4 need context (original CV, JD) that lives in the `load_customer_documents` tool span; new-style evaluators map only from the matched observation; legacy evaluators don't run on `events_only`.
- **Decision:** presenter attaches `customer_cv` + `job_description` from state as **metadata on its own span**. One span carries output + all context.
- Mechanism — spike picks:
  1. OTel span attributes `langfuse.observation.metadata.*` via `trace.get_current_span()` (preferred)
  2. ADK `Event.custom_metadata`, if the instrumentor propagates it
- Size guard: truncate metadata at ~20 KB/key.

## 4. Evaluator config

| Setting | Value |
|---|---|
| Target | Observations, live, 100% sampling |
| Filter #1–#4 | name = `agent_run [cv_presenter_agent]` (no-files runs never judged — span doesn't exist) |
| Filter #5 | `Is Root Observation = true` |
| Mapping #1–#4 | output → Output; context → Metadata `$.customer_cv` / `$.job_description` |
| Mapping #5 | query → Input `$.new_message.parts[0].text`; output → Output `$.content.parts[0].text` |
| Judge model | Vertex `google` connection, `gemini-2.5-flash` |
| Env filter | none initially; pytest runs get judged too |

## 5. Rollout

1. ~~v4 install~~ DONE 2026-07-31: clean install, org/project reseeded with the
   SAME keys (`.env` unchanged, no 401), Vertex connection recreated via API
   (ADC, location `global`). Remaining: recreate #5 in the UI (config snapshot
   in SPEC.md §7 item 3).
2. Spike: metadata variant 1, one run, inspect span; else variant 2.
3. Presenter metadata change, TDD (`tests/unit/test_presenter_agent.py`). Extends the committed presenter (`f46fb12`).
4. Create #1–#4 in UI; verify each variable preview shows real text.
5. E2E: one run → five scores; spot-check Faithfulness claim list against CV diff.
6. Update SPEC.md (evals section + presenter-metadata contract).

## 6. Verification

- Unit: metadata attached when state present; graceful when absent.
- Integration: `test_improve_cv_flow.py` unchanged (metadata additive).
- Live: 5 scores per happy-path run; reasoning references real CV content; #5 still scores no-files runs.

## 7. Secondary evaluators — future candidates

| Evaluator | Why | Trigger |
|---|---|---|
| Conciseness (Langfuse) | Reviser loops pad; padding is "faithful" so #1–#3 miss it | Observed length creep |
| User Disagreement/Distress (Langfuse) | User corrections = free ground truth; flags runs judges scored too generously | Multi-turn discussion loop (phase 2) |
| Out-of-Scope Request (Langfuse) | Users steering to non-CV work | Multi-user deployment |
| Topic Adherence (RAGAS) | Agent-side guardrail twin of the above | Public exposure |
| Goal Accuracy (RAGAS) | Trajectory-level goal completion on live traffic | Genuinely multi-step flows |
| Simple Criteria / Answer Critic (RAGAS) | Cheap one-off style rules (UK spelling, no first person) | A style guide to enforce |
| Critic-agreement meta-eval (custom) | Correlates critic's `exit_loop` approvals with judge scores — evaluates the pipeline's own quality gate | A few weeks of #1–#4 history |
| Context Precision/Recall (RAGAS) | Standard RAG metrics | Only if retrieval is added |

## 8. Future

- Retire metadata duplication if Langfuse adds cross-observation mapping.
- Dataset-backed regression runs reusing `cv_agent.evalset.json`: separate project.
