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
   the honest gold, 2026-08-01.)
2. **Complete** — nothing material from the customer's CV silently dropped.
3. **Tailored** — the job description's key requirements addressed with
   grounded evidence from real experience.
4. **Well-behaved conversation** — checks uploaded files before claiming or
   transferring; helpful no-files replies.
5. **Cost/latency** — monitored via Langfuse run charts; no hard thresholds
   at this scale.

The pipeline is non-deterministic (two runs invented *different* fake
metrics) and one metric hides another's regressions (a CV can be relevant
AND fabricated) — so each criterion gets its own scored, repeatable check.

## 2. Measure each criterion with the layered suite

| Layer | Runs | Catches |
|---|---|---|
| ADK evalset + integration test (pytest) | on demand, pre-commit | broken tool trajectory, state-flow regressions (criterion 4) |
| Experiments — `scripts/run_dataset_experiment.py` over dataset `regression-cases` | after every meaningful change | quality/truthfulness regressions vs hand-verified golds (criteria 1–3) |
| Live evaluators (Langfuse UI) | every real chat, automatic | drift in production-style use |

One judge per failure mode: `correctness` (vs gold, in code), `relevance`
(live), and — being built — `faithfulness` + `hallucination` (invention),
`completeness` (omission), `tailoring` (missing the point), fed by
presenter-span metadata.

## 3. Keep judges as versioned instruments

- Judge prompts live in Langfuse Prompt Management (`correctness-judge`, …);
  every score records `judge_prompt_version`, so a score shift is always
  attributable: pipeline change vs judge change.
- Every judge prompt carries a CV-domain worked example (fabrication →
  ~0.1). Calibration beats abstract rubrics — the generic template scored
  fabrication 0.5 until the worked example was added.
- Score names say the question asked (`correctness`, `relevance`); the
  lane/source lives in environment + metadata, never in the name.
- Judge model: `gemini-2.5-flash` via Vertex ADC, `location=global`
  (regional endpoints 429 under call bursts).

## 4. Hand-verify all ground truth

- Every fact in a gold must exist in its case's source CV — golds pass the
  same faithfulness bar as the pipeline. (The first gold was saved from an
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
- the **gold** (dataset item) — the reference itself breaks rule 4;
- the **judge** (new prompt version) — the scoring is miscalibrated.

Rerun with a change-named run and compare. Never tune two at once: the
0.5 → 0.1 shift (2026-08-01) was measurement honesty, not a pipeline
regression — interpretable only because gold and judge changes were named
and versioned separately.

## 6. Dev and prod share definitions, not judges

Decided by one question: **does the judge need ground truth?**

| Judge | Needs | Dev (experiments) | Prod (live) |
|---|---|---|---|
| `correctness` | gold answer | yes | impossible — no gold for live requests |
| `relevance` | query + output | redundant (correctness is stricter) | yes |
| `faithfulness` / `hallucination` | customer CV + output | yes | yes — same prompt, both surfaces |
| `completeness` | customer CV + output | yes | yes |
| `tailoring` | JD + output | yes | yes |

- Source-document judges run on BOTH surfaces from one shared definition
  (one evaluator binding, no environment filter) — dev and prod scores stay
  directly comparable.
- Gold-based judges are dev-only by nature; their prod counterpart is the
  source-document judges plus user signals.
- Never fork a judge's definition between surfaces. Different criteria =
  new judge with a new name.

## 7. Current status and next steps

Done: presenter ends every run with the CV + saves `improved_cv.md`; honest
gold for `senior-match`; `correctness` judge v3 (worked example);
`relevance` live evaluator; experiment runner with 429 retry and
`metadata.source=code`.

Next (detailed in the build plan):

1. Anti-fabrication rules in writer/reviser/critic prompts — expect
   `correctness` to climb from the 0.1 baseline.
2. Presenter metadata → the four source-document judges (dev + prod).
3. Ground-truth case library (`examples/cases/`) + dataset sync script.
4. Runner: per-case documents, `--run-name` flag.
5. Later (SPEC section 7): pytest env separation, ADK scores → Langfuse
   scores, user-simulation evals, ADK 2.x migration.
