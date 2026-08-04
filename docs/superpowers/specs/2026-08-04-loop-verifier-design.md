# Loop Verifier — Design

**Date:** 2026-08-04 · **Status:** agreed in discussion, pending review
**Scope:** two changes only — a verifier stage in the reviser loop, and one
new eval judge (`misrepresentation`). Guardrails (deterministic gates), fit
notes, and critic scoring are explicitly OUT of scope.

## 1. Problem

The evals prove the pipeline bends people to fit the JD when there is a
gap: it inflated a thin CV (hallucination 0.6) and demoted a staff
engineer to "seeking a Junior Support Engineer role" (hallucination 0.1).
The critic cannot police this: it judges tailoring quality AND truth, and
tailoring pressure wins — it has previously *demanded* ungrounded JD
vocabulary. Judges only measure after the fact; nothing inside the loop
blocks an untruthful draft from shipping.

## 2. Change 1 — verifier stage in the loop

New loop: **critic → verifier → reviser**. The critic is purely advisory;
the VERIFIER holds `exit_loop`. Each pass: critic critiques the draft,
verifier checks the same draft and — reading the critic's verdict — calls
`exit_loop` only when it finds no `fail` violations AND the critic set
`revision_required: false`. Otherwise the reviser applies both reports.

Moving the exit key solves the conflict of interest structurally: the
agent under tailoring pressure can no longer approve a release; the truth
checker holds the only key. It also avoids any first-pass missing-state
crash (nothing injects a report before it exists), and the draft that
ships is always one the verifier just passed.

- `verifier_agent` (LlmAgent, one call per iteration). Input: `cv_draft` +
  `customer_cv` (state injection, like the other agents). No JD — it has
  no opinion on tailoring; truth only.
- Prompt: `agents/verifier` in Prompt Management (versioned like the rest;
  local fallback + drift test).
- The rubric: four FIXED rules, named identically to the eval judges so a
  loop violation and an eval score mean the same defect:

| Rule | Offence |
|---|---|
| `faithfulness` | a fact not supported by the customer's CV |
| `hallucination` | framing that implies seniority/scale/expertise beyond it |
| `completeness` | a material item (job, degree, named project) missing |
| `misrepresentation` | the person's identity/seniority changed to fit the role — in either direction |

- Output (JSON, structured):

```json
{"pass": false,
 "violations": [
   {"rule": "faithfulness", "evidence": "improving query performance by 25%", "severity": "fail"},
   {"rule": "completeness", "evidence": "Personal Blog Platform project missing", "severity": "warn"}
 ]}
```

- Severities encode the asymmetry: fabrication/misrepresentation evidence
  is `fail`; soft adjectives are `warn`. Any `fail` blocks exit. The
  verifier may return `"pass": "cannot-determine"` instead of guessing
  (counts as not-clean; one extra iteration).
- State: verifier writes `verifier_report` (output_key). The reviser's
  instruction gains: fix every `fail` violation verbatim-quoted in
  `verifier_report`; violations take priority over the critic's stylistic
  feedback.
- Exit wiring: `exit_loop` moves from the critic to the verifier (the
  critic's tool list drops it). The verifier's prompt injects
  `{cv_criticism}` so it can require the critic's approval as well as its
  own clean pass. max_iterations=3 stays the ceiling; if the loop ends by
  ceiling with `fail`s outstanding, the presenter still emits the draft
  (today's behaviour) — blocking delivery entirely is a later product
  decision.
- Worked examples in the rubric prompt come from our own traces (25%
  metric, microservices, Elena's demotion) — calibration over exhortation.
- ADK note: plain LlmAgent inside the existing LoopAgent — nothing exotic;
  maps to a graph node under ADK 2.x.

## 3. Change 2 — `misrepresentation` eval judge

Fifth source-document judge in `evals/` (same shape as faithfulness):
prompt `judges/misrepresentation`, variables `{{customer_cv}}`,
`{{produced}}`. Question: is the person in the produced CV the same person,
at the same level, as in the original — neither inflated into a senior
specialist nor flattened into a junior applicant? Worked example each way
(John, Elena). Score 1.0 = same person presented at their true level.

Result: verifier rules and eval judges mirror exactly, four for four, one
shared vocabulary. The evals then answer "did the verifier let anything
through?" rather than discovering whole failure classes.

## 4. Costs

- +1 LLM call per loop iteration (worst case +3/run); judges stay on
  flash-lite; verifier uses the pipeline model (it gates delivery).
- Loop may run to ceiling more often initially (drafts that previously
  exited now get repaired) — slower runs, honester output.

## 5. Verification

- Unit: verifier JSON parses; reviser prompt receives the report; critic
  cannot exit while `pass` is false (instruction-level, asserted in the
  integration test's trajectory).
- Suite: rerun `regression-cases` — expect hallucination ≥ 0.8 on
  senior-match, misrepresentation ≥ 0.8 on overqualified, no regressions
  elsewhere. Baseline to beat is the 2026-08-03 board.
- The critic-agreement question ("is the critic doing its job?") becomes
  answerable later by comparing loop reports to eval scores.
