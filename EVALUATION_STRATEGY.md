# Evaluation Strategy — cv-agent

The strategy:

- LLM applications are non-deterministic — the same input produces varying
  outputs. Informal "vibe checks" cannot validate them; only rigorous,
  repeatable, scored evaluations can.
- An evaluation has three components: the **agent** (the versioned
  application under test), a **dataset** (curated cases with expert-labelled
  ground truth), and **scorers** (fast automated checks plus model-assisted
  LLM judges for subjective criteria).
- Define **success criteria** first: the requirements the application must
  meet, acceptable thresholds, and the critical failures it must never
  commit.
- Build a **comprehensive suite** combining automated checks and expert
  review, with evaluation code and criteria under version control.
- Create a **robust scoring system**: establish baselines, then iterate the
  scorers themselves as the application evolves.
- Build a **high-quality dataset** from real usage: curate continuously,
  capture edge cases and failure modes, and keep ground truth
  expert-verified.
- **Analyse results** to drive iteration: compare runs side by side, drill
  into individual examples, and measure every dimension that matters
  (quality, latency, cost, safety) — improving one metric can silently
  regress another.

Applied to this project, in numbered steps:

## 1. Success strategy

What a good run is, ranked; the first is non-negotiable:

1. **Truthful** — every fact in the improved CV exists in the customer's CV.
   No invented metrics, titles, technologies, or responsibilities. (Known
   failure mode: the pipeline currently fabricates — correctness 0.1 against
   the ground truths.)
2. **Complete** — nothing material from the customer's CV missing.
3. **Tailored** — the job description's key requirements addressed with
   grounded evidence from real experience.
4. **Rounded** — not solely shaped by the JD: skills from the CV that are
   not relevant to the role are still included, just never as the main
   focus.
5. **Honest about fit** — when the CV materially mismatches the role's key
   requirements, the user is told so, briefly and candidly, alongside the
   improved CV. Tailoring must never disguise a weak fit.
6. **Well-behaved conversation** — checks uploaded files before claiming or
   transferring; helpful no-files replies.
7. **Cost/latency** — monitored via Langfuse run charts; no hard thresholds
   at this scale.

The pipeline is non-deterministic (two runs invented *different* fake
metrics) and one metric hides another's regressions (a CV can be relevant
AND fabricated) — so each criterion gets its own scored, repeatable check.

## 2. Measure each criterion with the layered suite

| Layer | Runs | Catches |
|---|---|---|
| ADK evalset + integration test (pytest) | on demand, pre-commit | broken tool trajectory, state-flow regressions (criterion 4) |
| Experiments — `scripts/run_dataset_experiment.py` over dataset `regression-cases` | after every meaningful change | quality/truthfulness regressions vs hand-verified expected outputs (criteria 1–3) |
| Live evaluators (Langfuse UI) | every real chat, automatic | drift in production-style use |

One judge per failure mode: `correctness` (vs expected output, in code), `relevance`
(live), and — being built — `faithfulness` + `hallucination` (invention),
`completeness` (omission), `tailoring` (missing the point), and
`fit-disclosure` (weak fit not disclosed), fed by presenter-span metadata.

## 3. Keep judges as versioned instruments

- Judge prompts live in Langfuse Prompt Management (`correctness-judge`, …);
  every score records `judge_prompt_version`, so a score shift is always
  attributable: pipeline change vs judge change.
- Every judge prompt carries a CV-domain worked example (fabrication →
  ~0.1). Calibration beats abstract rubrics — the generic template scored
  fabrication 0.5 until the worked example was added.
- Score names say the question asked (`correctness`, `relevance`); the
  lane/source lives in environment + metadata, never in the name.
- Judge model: `gemini-2.5-flash-lite` via Vertex ADC, `location=global`
  (regional endpoints 429 under call bursts; lite halves quota contention).
- Evals are batch jobs: they must finish, not fail. All LLM calls (pipeline
  and judges) retry 429s with exponential backoff — slow on a starved-quota
  day is acceptable, a dead run is not. Exact delays live in code.

## 4. Hand-verify all ground truth

- Every fact in an expected output must exist in its case's source CV — expected outputs pass the
  same faithfulness bar as the pipeline. (The first expected output was saved from an
  embellished run and rewarded fabrication until hand-cleaned, 2026-08-01.)
- Curate from real traces (Add-to-Dataset on good runs), then edit by hand;
  never enshrine unreviewed pipeline output.
- Small and deliberate: 5–15 items, each testing a distinct pressure —
  `senior-match`, `career-switch` (mismatch honesty), `sparse-cv`
  (invention pressure), `overqualified` (omission pressure), no-files
  cases. Full inventory in the build plan.
- Run names are the changelog: name each experiment after what changed
  (`cleaned-dataset-v3-judge`), never just a timestamp.

## 5. Analyse: score → reason → verify → fix ONE thing

Read the judge's reason, verify its claim against the source documents,
then fix exactly one of:

- the **pipeline** (prompts/structure) — the reason shows real defects;
- the **expected output** (dataset item) — the reference itself breaks rule 4;
- the **judge** (new prompt version) — the scoring is miscalibrated.

Rerun with a change-named run and compare. Never tune two at once: the
0.5 → 0.1 shift (2026-08-01) was measurement honesty, not a pipeline
regression — interpretable only because expected output and judge changes were named
and versioned separately.

## 6. Dev and prod share definitions, not judges

Decided by one question: **does the judge need ground truth?**

| Judge | Needs | Dev (experiments) | Prod (live) |
|---|---|---|---|
| `correctness` | expected output | yes | impossible — no expected output for live requests |
| `relevance` | query + output | redundant (correctness is stricter) | yes |
| `faithfulness` / `hallucination` | customer CV + output | yes | yes — same prompt, both surfaces |
| `completeness` | customer CV + output | yes | yes |
| `tailoring` | JD + output | yes | yes |

- Source-document judges run on BOTH surfaces from one shared definition
  (one evaluator binding, no environment filter) — dev and prod scores stay
  directly comparable.
- Expected output-based judges are dev-only by nature; their prod counterpart is the
  source-document judges plus user feedback.
- Never fork a judge's definition between surfaces. Different criteria =
  new judge with a new name.

## 7. Current status and next steps

Done: presenter ends every run with the CV + saves `improved_cv.md`; honest
expected output for `senior-match`; `correctness` judge v3 (worked example);
`relevance` live evaluator; experiment runner with 429 retry and
`metadata.source=code`.

Next (detailed in the build plan):

1. Anti-fabrication rules in writer/reviser/critic prompts — expect
   `correctness` to climb from the 0.1 baseline.
2. Presenter metadata → the four source-document judges (dev + prod).
3. Ground-truth case library (`examples/cases/`) + dataset sync script.
4. Runner: per-case documents, `--run-name` flag.
5. Guardrails (SPEC section 7 item 2): LARGELY DONE 2026-08-06 — input
   chain (sanity, plausibility, Model Armor injection screening), output
   gates (grounding, format) in the presenter, runtime plugin (call
   ceiling, per-call timeout). Remaining: data-not-instructions rule in
   agent instructions, injection case in `regression-cases`, out-of-scope
   live evaluator.
6. Later (SPEC section 7): pytest env separation, ADK scores → Langfuse
   scores, user-simulation evals, ADK 2.x migration.

## 8. Advanced considerations

Agent evaluation extends beyond output quality into memory, tool use,
planning, multi-agent coordination, and human-agent interaction. Status of
each here — revisit when the trigger fires:

| Dimension | Status | Trigger to revisit |
|---|---|---|
| Tool use (selection, ordering, success rate) | Covered — ADK trajectory eval (exact match, load-before-transfer) | — |
| Multi-agent coordination (alignment, error propagation) | Implicit — state-chain assertions in the integration test | Critic-agreement meta-eval once judge history accumulates |
| Human-agent interaction (turn-to-repair, over/under-questioning) | Not yet relevant | Presenter phase 2 (post-delivery discussion loop) |
| Planning (goal achievement, plan feasibility) | Not applicable — fixed Sequential/Loop workflow, no dynamic planning | Pipeline gains dynamic routing (e.g. ADK 2.x graphs) |
| Memory management (recall, compression, forgetting) | Not applicable — single-session in-memory state | Persistent sessions / long-term memory added |
