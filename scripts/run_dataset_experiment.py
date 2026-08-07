"""Run a Langfuse experiment: execute the REAL cv-agent pipeline over every
item of a Langfuse dataset and link each result to the dataset run.

Unlike UI (prompt) experiments — which Langfuse executes as a bare
prompt+model and so cannot exercise the multi-agent workflow — this drives
the actual root agent exactly like main.py: example CV/JD artifacts are
pre-loaded per item, so "improve my CV" items take the happy path.

Usage:
    uv run python scripts/run_dataset_experiment.py [dataset_name] [run_name]

Defaults: dataset "regression-cases", run name "run-<timestamp>".
View results: Langfuse UI -> Datasets -> <dataset> -> Runs.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Runnable from anywhere: the repo root isn't on sys.path when invoked as
# `python scripts/run_dataset_experiment.py` (the package is not installed)
sys.path.insert(0, str(Path(__file__).parent.parent))

from cv_agents.config import Config

config = Config()
config.setup_environment()

from langfuse import get_client
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

# Langfuse client must exist before agents run: it registers the OTel exporter
langfuse = get_client()
GoogleADKInstrumentor().instrument()

from evals import ALL_EVALUATORS

from cv_agents.run_pipeline import run_once

PROJECT_ROOT = Path(__file__).parent.parent
USER_ID = "experiment_user"
CASES_DIR = PROJECT_ROOT / "examples" / "regression-cases"
# Uploaded-file names the tools expect; every case supplies both under these names
ARTIFACT_NAMES = ("sample_cv.txt", "sample_job_description.txt")
CASE_FILES = ("cv.txt", "jd.txt")


def resolve_item(item_input):
    """Map a dataset item input to (message, [(artifact_name, bytes), ...]).

    Dict inputs carry a `case` id resolving to examples/regression-cases/<case>/;
    `case: None` = no-files conversation item. Plain strings are the legacy
    senior-match shape."""
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


async def run_pipeline(message: str, artifacts) -> str:
    """One full agent run in a fresh session; returns the final response text."""
    _, final_text = await run_once(artifacts, message, user_id=USER_ID)
    return final_text


async def task(*, item, **kwargs) -> str:
    message, artifacts = resolve_item(item.input)
    print(f"\n=== item {item.id}: running pipeline...")
    # Vertex uses shared quota: bursts can 429 transiently. Retry with backoff
    # instead of failing the item (a 429 means "not this second", not "no").
    # Patient by design: evals are batch jobs that must finish, not fail.
    # Worst case ~25 min of waiting per item on a starved quota day.
    delays = (30, 60, 120, 240, 480, 600)
    for attempt, delay in enumerate((*delays, None)):
        try:
            return await run_pipeline(message, artifacts)
        except Exception as e:
            if "429" not in str(e) or delay is None:
                raise
            print(f"429 on item {item.id} (attempt {attempt + 1}); retrying in {delay}s...")
            await asyncio.sleep(delay)
    raise RuntimeError("unreachable")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", nargs="?", default="regression-cases")
    parser.add_argument(
        "run_name", nargs="?", default=f"run-{datetime.now():%Y%m%d_%H%M%S}",
        help="name the run after WHAT CHANGED, like a commit message",
    )
    parser.add_argument(
        "--items",
        help="comma-separated item ids to run (e.g. case-sparse-cv); default all",
    )
    args = parser.parse_args()
    dataset_name, run_name = args.dataset, args.run_name

    dataset = langfuse.get_dataset(dataset_name)
    if args.items:
        wanted = {i.strip() for i in args.items.split(",")}
        dataset.items = [i for i in dataset.items if i.id in wanted]
        missing = wanted - {i.id for i in dataset.items}
        if missing:
            sys.exit(f"unknown item ids: {', '.join(sorted(missing))}")
    print(f"Dataset '{dataset_name}': {len(dataset.items)} item(s). Running '{run_name}'...")

    result = dataset.run_experiment(
        name=run_name,
        description="Full cv-agent pipeline over dataset items",
        task=task,
        evaluators=ALL_EVALUATORS,
        max_concurrency=1,  # serial: avoids Vertex AI 429s (see CLAUDE.md)
        metadata={"source": "code"},  # filterable in the Experiments table
    )

    for item_result in result.item_results:
        output = str(item_result.output or "")
        print(f"\n--- item {item_result.item.id}")
        print(f"output ({len(output)} chars): {output[:200]}...")

    langfuse.flush()
    print(f"\nDone. View: {config.LANGFUSE_BASE_URL}/project/cv-agent-project/datasets")


if __name__ == "__main__":
    main()
