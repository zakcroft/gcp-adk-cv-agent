from google.adk import Agent
from google.adk.tools import exit_loop

from . import prompt
from cv_agents.config import Config
from cv_agents.remote_prompts import fetch_instruction

configs = Config()

critic_agent = Agent(
    model=configs.agent_settings.model,
    name="critic_agent",
    instruction=fetch_instruction("critic-instruction", prompt.CRITIC_INSTRUCTION),
    tools=[exit_loop],
    output_key="cv_criticism",
)
