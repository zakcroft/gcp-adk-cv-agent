from google.adk import Agent

from . import prompt
from cv_agents.config import Config

configs = Config()

# Writes back to cv_draft so the next loop iteration critiques the revised version
reviser_agent = Agent(
    model=configs.agent_settings.model,
    name="reviser_agent",
    instruction=prompt.REVISER_INSTRUCTION,
    output_key="cv_draft",
)
