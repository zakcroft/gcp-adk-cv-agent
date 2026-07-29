"""Trajectory and final-response evaluation for the CV agent.

Uses the same eval set as the CLI:
    uv run adk eval cv_agents eval/cv_agent.evalset.json \
        --config_file_path eval/test_config.json --print_detailed_results

AgentEvaluator automatically picks up eval/test_config.json (it looks for a
test_config.json next to the eval set file).
"""

from pathlib import Path

import pytest
from google.adk.evaluation.agent_evaluator import AgentEvaluator

from cv_agents.config import Config

PROJECT_ROOT = Path(__file__).parent.parent.parent


@pytest.mark.asyncio
async def test_tool_trajectory_and_final_response():
    Config().setup_environment()
    await AgentEvaluator.evaluate(
        agent_module="cv_agents",
        eval_dataset_file_path_or_dir=str(PROJECT_ROOT / "eval" / "cv_agent.evalset.json"),
    )
