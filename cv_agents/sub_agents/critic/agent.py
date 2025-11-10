from google.adk import Agent

from . import prompt
from cv_agents.config import Config

configs = Config()

critic_agent = Agent(
    model=configs.agent_settings.model,
    name="critic_agent",
    instruction=prompt.CRITIC_INSTRUCTION,
    output_key="cv_criticism",
)
