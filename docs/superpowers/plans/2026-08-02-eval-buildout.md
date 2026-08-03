# Evaluation Build-Out Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the pipeline truthful and measurably so: anti-fabrication prompts, presenter-span metadata, four truthfulness judges running on BOTH dev (experiments) and prod (live) surfaces, and a full set of ground-truth scenarios in `regression-cases`.

**Architecture:** Judges needing ground truth stay in the code runner (`correctness`); judges needing only source documents become Langfuse UI observation evaluators targeting `agent_run [cv_presenter_agent]`, fed by metadata the presenter attaches to its own span (source CV + JD). One evaluator config covers both surfaces by including both environments. Dataset items carry a `case` id resolving to per-case source documents on disk.

**Tech Stack:** Google ADK 1.17 (Python), Langfuse v4 self-hosted (`http://localhost:3000`), langfuse Python SDK v4, OpenInference `GoogleADKInstrumentor`, pytest + pytest-asyncio, Gemini 2.5 Flash via Vertex (`location=global`).

## Global Constraints

- **Commits require Zak's explicit go.** At every Commit step: show the diff summary, WAIT for approval. Never `git push`. No Claude co-author trailer.
- British English in agent-facing prose and CVs (SPEC section 8).
- Line length 100 (`black`/`ruff`).
- Vertex quota: run eval test files separately; experiment runner stays `max_concurrency=1`. 429 = quota, not a bug (CLAUDE.md).
- Prompt/agent edits require restarting any running chat process (instructions load at import).
- All Langfuse reads/writes use the project keys in `.env` (`pk-lf-277a…`/`sk-lf-26f5…`, `http://localhost:3000`). ClickHouse spot-checks: `docker exec langfuse-clickhouse-1 clickhouse-client`.
- Names are load-bearing: score names, span names, prompt names, dataset name (`regression-cases`) must not drift from this plan.
- Expected outputs rule (EVALUATION_STRATEGY section 6): every fact in an expected output must exist in its case's source CV. Zak reviews every expected output before it enters the dataset.

## Ground-truth scenario inventory (target end state of `regression-cases`)

| # | Case id | Source docs | Input message | Expected output | Tests |
|---|---|---|---|---|---|
| 1 | `senior-match` | existing `examples/sample_cv.txt` + `sample_job_description.txt` (backend dev → senior fintech role) | "make a cv for me on this day Friday" (keep as-is) | existing hand-cleaned expected output (2026-08-01) | the happy path; baseline continuity |
| 2 | `career-switch` | marketing manager CV + junior data-analyst JD | "please tailor my cv for this data analyst job" | hand-written: honest transferable-skills CV, no invented analytics experience | tailoring honesty under mismatch |
| 3 | `sparse-cv` | 8-line graduate CV (one internship, no metrics) + mid-level backend JD | "improve my cv for this role" | hand-written: modest, honest, well-structured; visibly thin | invention pressure — does the pipeline pad? |
| 4 | `overqualified` | staff-engineer CV (rich, real metrics) + junior support-engineer JD | "adapt my cv for this job" | hand-written: de-emphasised seniority WITHOUT deleting history | omission pressure — completeness under downscoping |
| 5 | `no-files-list` | none | "What files have I uploaded?" | verbatim reference reply from `cv_agent.evalset.json` (`list_files` case) | conversation path; correctness on refusal |
| 6 | `no-files-improve` | none | "Please improve my CV for the job description I provided." | verbatim reference reply from `cv_agent.evalset.json` (`improve_cv_missing_files` case) | must not transfer to workflow |

Cases 2–4 source docs + expected outputs are DRAFTED by the implementer and REVIEWED by Zak before the dataset items are created (Task 6 has an explicit review gate).

---

### Task 1: Anti-fabrication rules in writer and reviser prompts

**Files:**
- Modify: `cv_agents/sub_agents/writer/prompt.py`
- Modify: `cv_agents/sub_agents/reviser/prompt.py`
- Modify: `cv_agents/sub_agents/critic/prompt.py`

**Interfaces:**
- Produces: pipeline behaviour change only; no code API changes. Later tasks' scores depend on it.

- [ ] **Step 1: Read all three prompt files** to find where output rules live (each exports an `*_INSTRUCTION` string).

- [ ] **Step 2: Add the grounding rule to the writer instruction.** Append this block (verbatim) to `WRITER_INSTRUCTION`:

```
STRICT GROUNDING RULES (non-negotiable):
- Every fact MUST come from the customer's CV: job titles, employers, dates,
  technologies, qualifications, projects, and responsibilities.
- NEVER invent numbers, percentages, metrics, team sizes, or scale claims
  that are not in the customer's CV. A CV with no numbers stays a CV with
  no numbers.
- NEVER change or inflate job titles. The header title must be the title in
  the customer's CV.
- NEVER add technologies, certifications, or compliance standards the
  customer's CV does not mention.
- Tailor by reordering, emphasising, and rewording what is truly there —
  and by relating real experience to the job description — never by adding
  new claims.
```

- [ ] **Step 3: Add the same block to `REVISER_INSTRUCTION`**, plus this line (the reviser acts on criticism, so close that loophole):

```
If the criticism asks for improvements that would require inventing facts,
improve presentation instead and leave the facts unchanged.
```

- [ ] **Step 4: Add a grounding check to `CRITIC_INSTRUCTION`.** Append:

```
Also verify grounding: flag ANY fact in the draft (title, metric, number,
technology, certification) that does not appear in the customer's CV.
Fabricated facts are a mandatory revision_required=true.
```

- [ ] **Step 5: Run the integration test** (regression guard — pipeline still completes):

Run: `uv run pytest tests/eval/test_improve_cv_flow.py -q`
Expected: `1 passed` (~70s; a 429 means wait 1 min and rerun)

- [ ] **Step 6: Run the experiment** to measure the effect:

Run: `uv run python scripts/run_dataset_experiment.py regression-cases anti-fabrication-prompts`
Expected: completes; note the printed output.

- [ ] **Step 7: Verify the score moved.** Run:

```bash
docker exec langfuse-clickhouse-1 clickhouse-client -q "SELECT value, comment FROM scores WHERE name='correctness' ORDER BY timestamp DESC LIMIT 1 FORMAT Vertical"
```

Expected: value > 0.1 (baseline). Read the comment: fabrication complaints should be gone. If value ≤ 0.1, read the comment and the produced CV in the run — iterate the prompt wording (repeat Steps 2–7) before proceeding. Judge variance note: one run is indicative, not proof; if borderline, run once more.

- [ ] **Step 8: Commit (with Zak's go).** Show diff, wait for approval:

```bash
git add cv_agents/sub_agents/writer/prompt.py cv_agents/sub_agents/reviser/prompt.py cv_agents/sub_agents/critic/prompt.py
git commit -m "add strict grounding rules to writer, reviser, and critic prompts"
```

---

### Task 2: Presenter metadata — spike the propagation mechanism

**Files:**
- Create: `/tmp`-free scratch only (throwaway; nothing committed). Use the session scratchpad.

**Interfaces:**
- Produces: a DECISION — variant (a) OTel span attributes, or variant (b) `Event.custom_metadata` — consumed by Task 3.

- [ ] **Step 1: Try variant (a).** Temporarily add to `CvPresenterAgent._run_async_impl` (before the yield), guarded so failures can't break the run:

```python
from opentelemetry import trace as otel_trace

span = otel_trace.get_current_span()
if span is not None:
    span.set_attribute("langfuse.observation.metadata.spike", "variant-a")
```

- [ ] **Step 2: Run one pipeline pass:**

Run: `printf 'please improve my cv\nexit\n' | uv run main.py`

- [ ] **Step 3: Check the presenter span's metadata in ClickHouse** (wait ~15s for ingestion):

```bash
docker exec langfuse-clickhouse-1 clickhouse-client -q "SELECT metadata FROM events_full WHERE name like '%cv_presenter_agent%' ORDER BY start_time DESC LIMIT 1 FORMAT Vertical"
```

Expected: metadata map contains `spike: variant-a`. If YES → decision = variant (a); revert the temporary edit and go to Task 3. If NO → Step 4.

- [ ] **Step 4 (only if (a) failed): Try variant (b).** Replace the spike edit: add `custom_metadata={"spike": "variant-b"}` to the `Event(...)` constructor in `_text_event`. Repeat Steps 2–3 looking for `spike: variant-b`. If (b) also fails, STOP — report to Zak; the fallback per the design spec is legacy cross-span mapping, which changes Task 5 materially.

- [ ] **Step 5: Revert all spike edits** (`git checkout cv_agents/sub_agents/presenter/agent.py`), record the decision in the task notes.

---

### Task 3: Presenter attaches source documents as span metadata

**Files:**
- Modify: `cv_agents/sub_agents/presenter/agent.py`
- Test: `tests/unit/test_presenter_agent.py`

**Interfaces:**
- Consumes: Task 2's variant decision (steps below assume variant (a); if (b) won, set the same two keys via `Event.custom_metadata` instead — assertions unchanged).
- Produces: presenter span metadata keys `customer_cv` and `job_description` (each ≤ 20 000 chars), used by Task 5's evaluator mappings (`$.customer_cv`, `$.job_description`).

- [ ] **Step 1: Write the failing tests.** Append to `tests/unit/test_presenter_agent.py`:

```python
@pytest.mark.asyncio
async def test_attaches_source_documents_as_metadata(monkeypatch):
    captured = {}

    class FakeSpan:
        def set_attribute(self, key, value):
            captured[key] = value

    from cv_agents.sub_agents.presenter import agent as presenter_module

    monkeypatch.setattr(
        presenter_module.otel_trace, "get_current_span", lambda: FakeSpan()
    )
    ctx = await _make_context(
        {"cv_draft": FINAL_CV, "customer_cv": "original cv", "job_description": "the jd"}
    )

    async for _ in cv_presenter_agent.run_async(ctx):
        pass

    assert captured["langfuse.observation.metadata.customer_cv"] == "original cv"
    assert captured["langfuse.observation.metadata.job_description"] == "the jd"


@pytest.mark.asyncio
async def test_metadata_truncated_at_20k(monkeypatch):
    captured = {}

    class FakeSpan:
        def set_attribute(self, key, value):
            captured[key] = value

    from cv_agents.sub_agents.presenter import agent as presenter_module

    monkeypatch.setattr(
        presenter_module.otel_trace, "get_current_span", lambda: FakeSpan()
    )
    ctx = await _make_context({"cv_draft": FINAL_CV, "customer_cv": "x" * 30000})

    async for _ in cv_presenter_agent.run_async(ctx):
        pass

    assert len(captured["langfuse.observation.metadata.customer_cv"]) == 20000


@pytest.mark.asyncio
async def test_missing_documents_do_not_break_presentation(monkeypatch):
    from cv_agents.sub_agents.presenter import agent as presenter_module

    monkeypatch.setattr(presenter_module.otel_trace, "get_current_span", lambda: None)
    ctx = await _make_context({"cv_draft": FINAL_CV})

    events = [e async for e in cv_presenter_agent.run_async(ctx)]

    assert events[0].content.parts[0].text == FINAL_CV
```

- [ ] **Step 2: Run tests to verify they fail:**

Run: `uv run pytest tests/unit/test_presenter_agent.py -q`
Expected: 3 new tests FAIL (`otel_trace` attribute missing); 5 existing PASS.

- [ ] **Step 3: Implement.** In `cv_agents/sub_agents/presenter/agent.py` add import `from opentelemetry import trace as otel_trace` and, in `_run_async_impl` right before the artifact save, insert:

```python
        METADATA_MAX_CHARS = 20_000
        span = otel_trace.get_current_span()
        if span is not None:
            for key in ("customer_cv", "job_description"):
                value = ctx.session.state.get(key)
                if value:
                    span.set_attribute(
                        f"langfuse.observation.metadata.{key}",
                        str(value)[:METADATA_MAX_CHARS],
                    )
```

- [ ] **Step 4: Run tests to verify all pass:**

Run: `uv run pytest tests/unit/test_presenter_agent.py -q`
Expected: 8 passed.

- [ ] **Step 5: End-to-end verification.** One pipeline pass, then confirm real metadata landed:

```bash
printf 'please improve my cv\nexit\n' | uv run main.py
sleep 15
docker exec langfuse-clickhouse-1 clickhouse-client -q "SELECT mapKeys(metadata), substring(metadata['customer_cv'],1,60) FROM events_full WHERE name LIKE '%cv_presenter_agent%' ORDER BY start_time DESC LIMIT 1 FORMAT Vertical"
```

Expected: keys include `customer_cv`, `job_description`; preview shows John Smith's original CV text.

- [ ] **Step 6: Commit (with Zak's go):**

```bash
git add cv_agents/sub_agents/presenter/agent.py tests/unit/test_presenter_agent.py
git commit -m "presenter attaches source documents as span metadata for evaluators"
```

---

### Task 4: Shared judge prompts for the source-document judges

**Files:**
- No repo files. Creates three Langfuse Prompt Management prompts (source of truth for BOTH surfaces). Use a throwaway script in the scratchpad calling `langfuse.create_prompt(...)` (pattern: how `correctness-judge` v3 was created).

**Interfaces:**
- Produces: prompts `faithfulness-judge`, `completeness-judge`, `tailoring-judge` — each `type='text'`, label `production`, variables exactly `{{customer_cv}}`, `{{job_description}}`, `{{produced}}`. Consumed by Task 5 (pasted into UI evaluators) and available to any future code judge.

- [ ] **Step 1: Create `faithfulness-judge` v1** with this text:

```
You are auditing a CV rewrite for truthfulness. Compare the PRODUCED CV
against the CUSTOMER'S ORIGINAL CV — the only source of facts.

Evaluate faithfulness on a continuous scale from 0 to 1. The PRODUCED CV is
faithful (Score: 1) only if every fact it presents — job titles, employers,
dates, numbers, metrics, technologies, certifications, responsibilities —
appears in or is directly supported by the ORIGINAL CV. Rewording,
restructuring, and emphasis are always allowed and never reduce the score.

Scoring guide:
- 1.0: fully grounded — no claim goes beyond the original
- 0.5: minor embellishment — inflated adjectives or stretched seniority, but
  no invented concrete facts
- 0.0-0.2: fabrication — invented numbers, metrics, titles, technologies,
  certifications, or responsibilities

Example:
Original (excerpt):
Software Engineer | TechCorp Ltd
- Worked on backend systems and APIs
Produced (excerpt):
Senior Backend Engineer | TechCorp Ltd
- Architected microservices handling 5 million requests daily
Score: 0.1
Reasoning: The produced CV inflates the job title and invents a scale metric
(5 million requests) with no basis in the original.

ORIGINAL CV:
{{customer_cv}}

PRODUCED CV:
{{produced}}

Reply with ONLY a JSON object: {"score": <float>, "reason": "<one sentence>"}
```

- [ ] **Step 2: Create `completeness-judge` v1** with this text:

```
You are checking a CV rewrite for silent omissions. Compare the PRODUCED CV
against the CUSTOMER'S ORIGINAL CV.

List the material items in the ORIGINAL CV: every job, qualification, named
project, and distinct skill group. Evaluate completeness on a continuous
scale from 0 to 1 as the fraction of those items that are retained (in any
wording) in the PRODUCED CV. Reordering and condensing are fine; removal is
not. A missing job, degree, or named project caps the score at 0.5.

Example:
Original items: 2 jobs, 1 degree, 2 projects, 5 skill groups (10 items).
Produced: both jobs, the degree, 1 of 2 projects, all skills (9 of 10, but a
named project is missing).
Score: 0.5
Reasoning: The Personal Blog Platform project was dropped entirely; a missing
named project caps the score at 0.5.

ORIGINAL CV:
{{customer_cv}}

PRODUCED CV:
{{produced}}

Reply with ONLY a JSON object: {"score": <float>, "reason": "<one sentence>"}
```

- [ ] **Step 3: Create `tailoring-judge` v1** with this text:

```
You are judging how well a CV rewrite targets a specific job description.

Extract the 5-8 key requirements of the JOB DESCRIPTION (skills,
technologies, responsibilities, seniority). Evaluate tailoring on a
continuous scale from 0 to 1: the weighted fraction of those requirements
the PRODUCED CV addresses with concrete, relevant content. Give NO credit
for a requirement addressed only by an unsupported claim (a skill merely
named with no supporting experience anywhere in the CV). A generic CV that
ignores the job description scores near 0 even if well written.

ORIGINAL JOB DESCRIPTION:
{{job_description}}

PRODUCED CV:
{{produced}}

Reply with ONLY a JSON object: {"score": <float>, "reason": "<one sentence>"}
```

- [ ] **Step 4: Verify all three exist:**

```bash
curl -s -u "$LF_KEYS" "http://localhost:3000/api/public/v2/prompts" | python3 -c "import json,sys; [print(p['name'], p['labels']) for p in json.load(sys.stdin)['data']]"
```

Expected: `faithfulness-judge`, `completeness-judge`, `tailoring-judge` each with `production`; `correctness-judge` untouched.

---

### Task 5: Four UI evaluators on the presenter span (dev + prod in one binding)

**Files:**
- No repo files — Langfuse UI configuration (Zak drives the UI; implementer supplies exact values and verifies results). Config recorded in SPEC by Task 9.

**Interfaces:**
- Consumes: Task 3's metadata keys; Task 4's prompt texts.
- Produces: scores `faithfulness`, `hallucination`, `completeness`, `tailoring` on every happy-path run in BOTH environments.

Shared config for all four (UI → Evaluators → Set up evaluator):

| Setting | Value |
|---|---|
| Run on | Observations, live ON |
| Filter | Name = `agent_run [cv_presenter_agent]` (only exists on happy-path runs — no-files runs are never judged by these) |
| Environment filter | NONE (so both `default` AND `sdk-experiment` are judged — this IS the dev/prod parity) |
| Sampling / delay | 100% / 30s |
| Judge model | `google` connection, `gemini-2.5-flash` |
| Variable mapping | `{{produced}}` ← Output, JSONPath `$.content.parts[0].text`; `{{customer_cv}}` ← Metadata, JSONPath `$.customer_cv`; `{{job_description}}` ← Metadata, JSONPath `$.job_description` |

- [ ] **Step 1: Evaluator `faithfulness`** — Custom template, paste Task 4's `faithfulness-judge` v1 text (note "synced from faithfulness-judge v1" in the description; if the PM prompt is ever versioned up, re-paste here — parity rule, EVALUATION_STRATEGY section 8). Generated score name: `faithfulness`.

- [ ] **Step 2: Evaluator `hallucination`** — Langfuse managed Hallucination template; map its context variable to Metadata `$.customer_cv`, its output variable to Output `$.content.parts[0].text`. Generated score name: `hallucination`. (Cross-check for faithfulness — different template family, same question.)

- [ ] **Step 3: Evaluator `completeness`** — Custom template = `completeness-judge` v1 text. Score name: `completeness`.

- [ ] **Step 4: Evaluator `tailoring`** — Custom template = `tailoring-judge` v1 text. Score name: `tailoring`.

- [ ] **Step 5: Verify variable previews** in each wizard show real text (CV/JD content, not `{}`) before saving — the preview uses the presenter spans created in Task 3 Step 5.

- [ ] **Step 6: End-to-end verification.** One live run + one experiment run:

```bash
printf 'please improve my cv\nexit\n' | uv run main.py
uv run python scripts/run_dataset_experiment.py regression-cases four-judges-live
sleep 90
docker exec langfuse-clickhouse-1 clickhouse-client -q "SELECT name, environment, value, substring(comment,1,60) FROM scores WHERE timestamp > now() - INTERVAL 10 MINUTE ORDER BY name FORMAT PrettyCompact"
```

Expected: `faithfulness`, `hallucination`, `completeness`, `tailoring` present for BOTH `default` and `sdk-experiment` environments (plus `correctness` on the experiment). Read each comment for sanity — reasons must reference actual CV content.

---

### Task 6: Ground-truth scenarios — source documents, expected outputs, dataset items

**Files:**
- Create: `examples/cases/career-switch/cv.txt`, `examples/cases/career-switch/jd.txt`, `examples/cases/career-switch/expected output.md`
- Create: `examples/cases/sparse-cv/{cv.txt,jd.txt,expected output.md}`
- Create: `examples/cases/overqualified/{cv.txt,jd.txt,expected output.md}`
- Create: `examples/cases/senior-match/{cv.txt,jd.txt,expected output.md}` (copies of the existing sample pair + current expected output, so every case is self-contained)
- Create: `scripts/sync_dataset.py`

**Interfaces:**
- Consumes: scenario inventory table above.
- Produces: dataset items whose `input` is `{"message": <str>, "case": <case id or null>}`; `expected_output` = expected output text. Task 7's runner depends on this exact input shape.

- [ ] **Step 1: Draft the three new case document pairs** (realistic, UK-flavoured, fictional people — NOT John Smith; each CV deliberately matching its scenario's pressure). Career-switch: marketing manager, 6 years, zero analytics tooling. Sparse: graduate, one internship, ≤ 8 content lines. Overqualified: staff engineer, 12 years, genuine metrics in the ORIGINAL (so the expected output may keep them).

- [ ] **Step 2: Draft each expected output** (`expected output.md`) obeying the expected-output rule: facts only from that case's `cv.txt`; tailoring via structure/emphasis; British English. For `overqualified`, real original metrics are retained — this tests that judges allow grounded numbers.

- [ ] **Step 3: REVIEW GATE — present all drafts to Zak.** Show each cv/jd/expected output. Do not proceed until each expected output is approved. (Approved expected outputs are the constitution of the eval suite.)

- [ ] **Step 4: Write `scripts/sync_dataset.py`** — idempotent dataset sync (same header pattern as `run_dataset_experiment.py`: sys.path insert, Config().setup_environment(), get_client):

```python
"""Sync regression-cases dataset items from examples/cases/ + the ADK evalset.

Idempotent: item ids are stable (case ids), so re-running upserts in place.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cv_agents.config import Config

Config().setup_environment()

from langfuse import get_client

PROJECT_ROOT = Path(__file__).parent.parent
CASES_DIR = PROJECT_ROOT / "examples" / "cases"
EVALSET = PROJECT_ROOT / "tests" / "eval" / "data" / "cv_agent.evalset.json"
DATASET = "regression-cases"

CASE_MESSAGES = {
    "senior-match": "make a cv for me on this day Friday",
    "career-switch": "please tailor my cv for this data analyst job",
    "sparse-cv": "improve my cv for this role",
    "overqualified": "adapt my cv for this job",
}


def main() -> None:
    langfuse = get_client()

    for case_id, message in CASE_MESSAGES.items():
        expected output = (CASES_DIR / case_id / "expected output.md").read_text()
        langfuse.create_dataset_item(
            dataset_name=DATASET,
            id=f"case-{case_id}",
            input={"message": message, "case": case_id},
            expected_output=expected output,
        )
        print(f"synced case-{case_id}")

    evalset = json.loads(EVALSET.read_text())
    for eval_case in evalset["eval_cases"]:
        conv = eval_case["conversation"][0]
        langfuse.create_dataset_item(
            dataset_name=DATASET,
            id=f"nofiles-{eval_case['eval_id']}",
            input={
                "message": conv["user_content"]["parts"][0]["text"],
                "case": None,
            },
            expected_output=conv["final_response"]["parts"][0]["text"],
        )
        print(f"synced nofiles-{eval_case['eval_id']}")

    langfuse.flush()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Migration note — the legacy item.** The original item (`ffbeed4f-…`, plain-string input) becomes redundant once `case-senior-match` exists with the same expected output. Ask Zak: archive it (Langfuse UI → item → archive) to avoid double-running the same case. Do not delete without his go.

- [ ] **Step 6: Run the sync:**

Run: `uv run python scripts/sync_dataset.py`
Expected: 6 lines (`synced case-…` ×4, `synced nofiles-…` ×2). Verify in UI: dataset shows the new items with structured inputs.

- [ ] **Step 7: Commit (with Zak's go):**

```bash
git add examples/cases scripts/sync_dataset.py
git commit -m "add ground-truth case library and dataset sync script"
```

---

### Task 7: Runner — per-item documents and --run-name flag

**Files:**
- Modify: `scripts/run_dataset_experiment.py`
- Test: `tests/unit/test_experiment_runner.py` (create)

**Interfaces:**
- Consumes: Task 6's item input shape `{"message": str, "case": str|None}`; case docs at `examples/cases/<case>/{cv.txt,jd.txt}`.
- Produces: CLI `uv run python scripts/run_dataset_experiment.py [dataset] --run-name NAME`; function `resolve_item(item_input) -> tuple[str, list[tuple[str, bytes]]]` returning (message, artifacts-to-preload).

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_experiment_runner.py`):

```python
"""resolve_item maps a dataset item's input to (message, artifacts to preload)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.run_dataset_experiment import resolve_item


def test_case_item_loads_its_own_documents():
    message, artifacts = resolve_item(
        {"message": "improve my cv", "case": "senior-match"}
    )
    assert message == "improve my cv"
    names = [name for name, _ in artifacts]
    assert names == ["sample_cv.txt", "sample_job_description.txt"]
    assert b"John Smith" in artifacts[0][1]


def test_no_files_item_preloads_nothing():
    message, artifacts = resolve_item({"message": "What files?", "case": None})
    assert message == "What files?"
    assert artifacts == []


def test_legacy_string_input_uses_default_documents():
    message, artifacts = resolve_item("make a cv for me")
    assert message == "make a cv for me"
    assert len(artifacts) == 2
```

- [ ] **Step 2: Run tests to verify they fail:**

Run: `uv run pytest tests/unit/test_experiment_runner.py -q`
Expected: FAIL — `cannot import name 'resolve_item'`.

- [ ] **Step 3: Implement in `scripts/run_dataset_experiment.py`.** Add:

```python
CASES_DIR = PROJECT_ROOT / "examples" / "cases"
# Uploaded-file names the tools expect; every case supplies both under these names
ARTIFACT_NAMES = ("sample_cv.txt", "sample_job_description.txt")
CASE_FILES = ("cv.txt", "jd.txt")


def resolve_item(item_input):
    """Map a dataset item input to (message, [(artifact_name, bytes), ...])."""
    if isinstance(item_input, str):
        case = "senior-match"
        message = item_input
    else:
        case = item_input.get("case")
        message = item_input["message"]

    if case is None:
        return message, []

    artifacts = [
        (artifact_name, (CASES_DIR / case / case_file).read_bytes())
        for artifact_name, case_file in zip(ARTIFACT_NAMES, CASE_FILES)
    ]
    return message, artifacts
```

Rewire `run_pipeline(question)` → `run_pipeline(message, artifacts)`: replace the hardcoded `EXAMPLE_FILES` loop with a loop over the passed `artifacts` (same `save_artifact` call, `filename=artifact_name`). Rewire `task`:

```python
async def task(*, item, **kwargs) -> str:
    message, artifacts = resolve_item(item.input)
    ...retry loop unchanged, calling run_pipeline(message, artifacts)...
```

Replace positional `sys.argv` parsing in `main()` with argparse:

```python
import argparse

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("dataset", nargs="?", default="regression-cases")
parser.add_argument("--run-name", default=f"run-{datetime.now():%Y%m%d_%H%M%S}")
args = parser.parse_args()
```

(`senior-match` docs are byte-identical to the old hardcoded pair, so legacy behaviour is preserved.)

- [ ] **Step 4: Run unit tests to verify they pass:**

Run: `uv run pytest tests/unit/test_experiment_runner.py -q`
Expected: 3 passed.

- [ ] **Step 5: Full-suite run:**

Run: `uv run python scripts/run_dataset_experiment.py regression-cases --run-name full-suite-first-run`
Expected: 6 items complete (happy-path items several minutes each; serial). No-files items return the "please upload" reply fast.

- [ ] **Step 6: Verify scores per item type** (after ~2 min for UI judges):

```bash
docker exec langfuse-clickhouse-1 clickhouse-client -q "SELECT name, count() FROM scores WHERE timestamp > now() - INTERVAL 30 MINUTE GROUP BY name FORMAT PrettyCompact"
```

Expected: `correctness` = 6; `faithfulness`/`hallucination`/`completeness`/`tailoring` = 4 each (happy-path items only, both would-be environments — here `sdk-experiment`).

- [ ] **Step 7: Commit (with Zak's go):**

```bash
git add scripts/run_dataset_experiment.py tests/unit/test_experiment_runner.py
git commit -m "runner: per-case documents, no-files items, --run-name flag"
```

---

### Task 8: Fit disclosure — behaviour and judge

**Files:**
- Modify: `cv_agents/sub_agents/writer/prompt.py` (fit note instruction)
- Modify: `cv_agents/sub_agents/presenter/agent.py` + `tests/unit/test_presenter_agent.py` (pass note through)
- No repo files for the judge: one Langfuse prompt + one UI evaluator.

**Interfaces:**
- Consumes: Task 3's metadata mechanism, Task 5's evaluator pattern.
- Produces: state key `fit_note` (writer, may be empty); presenter emits it after the CV as a separate paragraph and adds metadata key `fit_note`; score `fit-disclosure`.

- [ ] **Step 1: Writer assesses fit.** Append to `WRITER_INSTRUCTION` (after the grounding rules):

```
FIT ASSESSMENT:
After the CV, on a new line starting exactly "FIT NOTE:", add one candid
sentence ONLY IF the customer's CV materially lacks the role's key
requirements (missing core skills, seniority gap, wrong domain). If the fit
is reasonable, do not add a fit note at all. Never soften the CV itself to
justify the note.
```

- [ ] **Step 2: Presenter splits the note.** TDD in `tests/unit/test_presenter_agent.py`: `cv_draft` containing a `FIT NOTE:` line → presenter emits CV text and the note as the final paragraph, sets metadata key `fit_note`; no line → no note, no metadata key. Implement by splitting on `\nFIT NOTE:` in `_run_async_impl`.

- [ ] **Step 3: Judge prompt `fit-disclosure-judge` v1** (Prompt Management, label `production`), variables `{{customer_cv}}`, `{{job_description}}`, `{{produced}}`:

```
You are checking whether a CV service was honest about job fit.

Compare the CUSTOMER'S ORIGINAL CV against the JOB DESCRIPTION. Decide if
there is a MATERIAL mismatch: core required skills absent from the CV, a
clear seniority gap, or a different domain. Then check the PRODUCED output.

Score:
- 1.0: material mismatch AND the output includes a candid fit note naming
  the real gaps (or: no material mismatch and no note — also 1.0)
- 0.5: mismatch disclosed but vague or buried
- 0.0: material mismatch with no disclosure, or a note that misstates the
  gaps

ORIGINAL CV:
{{customer_cv}}

JOB DESCRIPTION:
{{job_description}}

PRODUCED OUTPUT:
{{produced}}

Reply with ONLY a JSON object: {"score": <float>, "reason": "<one sentence>"}
```

- [ ] **Step 4: UI evaluator `fit-disclosure`** — same binding as Task 5's table (presenter span, no env filter, same mappings, `{{produced}}` ← Output `$.content.parts[0].text`).

- [ ] **Step 5: Verify on the two fixture cases.** Run `career-switch` (expects a note) and `senior-match` (expects none) via the runner; check both score 1.0 and the reasons cite the right gaps:

```bash
uv run python scripts/run_dataset_experiment.py regression-cases --run-name fit-disclosure-check
```

- [ ] **Step 6: Commit (with Zak's go):**

```bash
git add cv_agents/sub_agents/writer/prompt.py cv_agents/sub_agents/presenter/agent.py tests/unit/test_presenter_agent.py
git commit -m "writer discloses weak job fit; presenter surfaces the note; fit-disclosure judge"
```

---

### Task 9: Documentation reconciliation

**Files:**
- Modify: `SPEC.md` (section 6 two-lane model → add the four judges + their config snapshot, dataset item shape, case library; section 7 mark items 1/2/5 done)
- Modify: `EVALUATION_STRATEGY.md` (section 4 planned additions → live; section 10 tick 1–3)
- Modify: `CLAUDE.md` (runner command line gains `--run-name`)

**Interfaces:** none — text only. Follow the terse style (tables + bullets).

- [ ] **Step 1: Update the three files** to match what shipped (exact evaluator configs from Task 5's table, item input shape from Task 6, scenario inventory as the now-current dataset contents).

- [ ] **Step 2: Self-check** — grep the docs for the old claims: `grep -n 'sample_cv.txt\|positional\|planned' SPEC.md EVALUATION_STRATEGY.md CLAUDE.md` and reconcile hits.

- [ ] **Step 3: Commit (with Zak's go):**

```bash
git add SPEC.md EVALUATION_STRATEGY.md CLAUDE.md
git commit -m "update spec and strategy for the four-judge eval suite"
```

---

## Self-review notes

- Spec coverage: strategy section 10.1 → Task 1; section 10.2 → Tasks 2–5; section 10.3 → Task 6; section 10.4 runner ergonomics → Task 7 (`--run-name`), pytest env separation and ADK-scores→Langfuse deliberately NOT in this plan (separate small chores, SPEC section 7); dev/prod parity section 8 → Task 5 env-filter-none decision; eval-suite design section 3 metadata → Tasks 2–3; section 4 configs → Task 5.
- Known judgement points left to Zak: expected output approvals (Task 6 Step 3), legacy item archival (Task 6 Step 5), every commit.
- Type consistency: `resolve_item` shape defined in Task 7 matches Task 6's item input `{"message", "case"}`; metadata keys in Task 3 match Task 5 JSONPaths.
