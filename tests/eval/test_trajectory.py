"""Trajectory and final-response evaluation for the CV agent.

Eval data lives in tests/eval/data/. AgentEvaluator automatically picks up
the test_config.json criteria file sitting next to the eval set file.

Also runnable via the ADK CLI:
    PYTHONPATH=$PWD uv run adk eval cv_agents tests/eval/data/cv_agent.evalset.json \
        --config_file_path tests/eval/data/test_config.json --print_detailed_results
"""

from pathlib import Path

import pytest
from google.adk.evaluation.agent_evaluator import AgentEvaluator

from cv_agents.config import Config

DATA_DIR = Path(__file__).parent / "data"


@pytest.mark.asyncio
async def test_tool_trajectory_and_final_response():
    Config().setup_environment()
    await AgentEvaluator.evaluate(
        agent_module="cv_agents",
        eval_dataset_file_path_or_dir=str(DATA_DIR / "cv_agent.evalset.json"),
    )
