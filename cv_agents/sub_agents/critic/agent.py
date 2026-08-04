from google.adk import Agent

from . import prompt
from cv_agents.config import Config
from cv_agents.remote_prompts import fetch_instruction

configs = Config()

# Purely advisory since the verifier took over the loop exit: the critic
# judges quality but cannot approve a release (conflict-of-interest fix).
critic_agent = Agent(
    model=configs.agent_settings.model,
    name="critic_agent",
    instruction=fetch_instruction("agents/critic", prompt.CRITIC_INSTRUCTION),
    output_key="cv_criticism",
)
