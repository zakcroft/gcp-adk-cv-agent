from google.adk import Agent
from google.adk.tools import exit_loop

from . import prompt
from cv_agents.config import Config
from cv_agents.remote_prompts import fetch_instruction

configs = Config()

# The truth gate of the reviser loop. Purely advisory critic, gated exit:
# this agent holds exit_loop and only approves when its four-rule check is
# clean AND the critic asked for no revision (see the design doc,
# docs/superpowers/specs/2026-08-04-loop-verifier-design.md).
verifier_agent = Agent(
    model=configs.agent_settings.model,
    name="verifier_agent",
    description="Checks the CV draft is truthful to the customer's CV; holds the loop exit.",
    instruction=fetch_instruction("agents/verifier", prompt.VERIFIER_INSTRUCTION),
    tools=[exit_loop],
    output_key="verifier_report",
)
