from google.adk import Agent

from . import prompt
from cv_agents.config import Config
from cv_agents.remote_prompts import fetch_instruction

configs = Config()

# Writes back to cv_draft so the next loop iteration critiques the revised version
reviser_agent = Agent(
    model=configs.agent_settings.model,
    name="reviser_agent",
    instruction=fetch_instruction("reviser-instruction", prompt.REVISER_INSTRUCTION),
    output_key="cv_draft",
)
