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
import uuid
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

from google.adk.artifacts import InMemoryArtifactService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from evals import ALL_EVALUATORS

from cv_agents.agent import root_agent

PROJECT_ROOT = Path(__file__).parent.parent
USER_ID = "experiment_user"
EXAMPLE_FILES = ("sample_cv.txt", "sample_job_description.txt")


async def run_pipeline(question: str) -> str:
    """One full agent run in a fresh session; returns the final response text."""
    session_id = f"experiment_{uuid.uuid4().hex[:8]}"
    session_service = InMemorySessionService()
    artifact_service = InMemoryArtifactService()

    await session_service.create_session(
        app_name=config.app_name, user_id=USER_ID, session_id=session_id
    )
    for filename in EXAMPLE_FILES:
        content = (PROJECT_ROOT / "examples" / filename).read_bytes()
        await artifact_service.save_artifact(
            app_name=config.app_name,
            user_id=USER_ID,
            session_id=session_id,
            filename=filename,
            artifact=types.Part.from_bytes(data=content, mime_type="text/plain"),
        )

    runner = Runner(
        agent=root_agent,
        app_name=config.app_name,
        artifact_service=artifact_service,
        session_service=session_service,
    )

    final_text = ""
    message = types.Content(role="user", parts=[types.Part(text=question)])
    async for event in runner.run_async(
        user_id=USER_ID, session_id=session_id, new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            if event.content.parts[0].text:
                final_text = event.content.parts[0].text
    return final_text


async def task(*, item, **kwargs) -> str:
    question = item.input if isinstance(item.input, str) else str(item.input)
    # Vertex uses shared quota: bursts can 429 transiently. Retry with backoff
    # instead of failing the item (a 429 means "not this second", not "no").
    delays = (30, 60, 120)
    for attempt, delay in enumerate((*delays, None)):
        try:
            return await run_pipeline(question)
        except Exception as e:
            if "429" not in str(e) or delay is None:
                raise
            print(f"429 on item {item.id} (attempt {attempt + 1}); retrying in {delay}s...")
            await asyncio.sleep(delay)
    raise RuntimeError("unreachable")


def main() -> None:
    dataset_name = sys.argv[1] if len(sys.argv) > 1 else "regression-cases"
    run_name = sys.argv[2] if len(sys.argv) > 2 else f"run-{datetime.now():%Y%m%d_%H%M%S}"

    dataset = langfuse.get_dataset(dataset_name)
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
