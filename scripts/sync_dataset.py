"""Sync regression-cases dataset items from examples/cases/.

Each case directory provides cv.txt + jd.txt (source documents) and
expected_output.md (hand-verified reference). No-files conversation cases
come from the ADK evalset so one source of truth feeds both pytest and
experiments.

Idempotent: item ids are stable (case-<name>), so re-running upserts.

Usage: uv run python scripts/sync_dataset.py
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
    "senior-match": "Tailor a cv for me from the job description and my CV",
    "career-switch": (
        "I'm looking to move from marketing into data analysis. "
        "Can you tailor my CV for this junior data analyst role?"
    ),
    "sparse-cv": (
        "I graduated last year and this is my first proper application. "
        "Please improve my CV for this backend engineer job."
    ),
    "overqualified": (
        "I want a change of pace. Can you adapt my CV for this support engineer role?"
    ),
    "senior-frontend": (
        "I've found a senior frontend role in Bristol that looks like a good "
        "step up. Can you tailor my CV for it?"
    ),
    "agentic-ai": (
        "This agentic AI engineer role looks exciting but I'm not sure my AI "
        "experience is deep enough. Can you tailor my CV for it?"
    ),
}


def main() -> None:
    langfuse = get_client()

    for case_id, message in CASE_MESSAGES.items():
        expected = (CASES_DIR / case_id / "expected_output.md").read_text()
        langfuse.create_dataset_item(
            dataset_name=DATASET,
            id=f"case-{case_id}",
            input={"message": message, "case": case_id},
            expected_output=expected,
        )
        print(f"synced case-{case_id}")

    evalset = json.loads(EVALSET.read_text())
    for eval_case in evalset["eval_cases"]:
        conversation = eval_case["conversation"][0]
        langfuse.create_dataset_item(
            dataset_name=DATASET,
            id=f"nofiles-{eval_case['eval_id']}",
            input={
                "message": conversation["user_content"]["parts"][0]["text"],
                "case": None,
            },
            expected_output=conversation["final_response"]["parts"][0]["text"],
        )
        print(f"synced nofiles-{eval_case['eval_id']}")

    langfuse.flush()
    print("done")


if __name__ == "__main__":
    main()
