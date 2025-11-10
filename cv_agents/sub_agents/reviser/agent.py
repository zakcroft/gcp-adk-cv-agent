from google.adk import Agent

from . import prompt
from cv_agents.config import Config

configs = Config()

reviser_agent = Agent(
    model=configs.agent_settings.model,
    name="reviser_agent",
    instruction=prompt.REVISER_INSTRUCTION,
    output_key="revised_CV",
)
