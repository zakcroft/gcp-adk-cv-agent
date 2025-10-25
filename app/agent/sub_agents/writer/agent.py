from google.adk.agents import Agent, LoopAgent, SequentialAgent
from google.adk.tools import google_search

from app.agent.sub_agents.critic.agent import critic_agent
from app.agent.sub_agents.reviser.agent import reviser_agent

from app.agent.config import Config

from . import prompt

configs = Config()


writer = Agent(
    model=configs.agent_settings.model,
    name="writer",
    description="Writes a technical blog post.",
    instruction=prompt.WRITER_INSTRUCTION,
    tools=[google_search],
    output_key="initial_draft",
)

# TODO - add a termination condition - validated flag is made by reviser.
reviser = LoopAgent(
    name="reviser",
    description="A CV reviser",
    sub_agents=[critic_agent, reviser_agent],
    max_iterations=3,
)

cv_writer_agent = SequentialAgent(
    name="cv_writer_agent", description="Cv writer agent", sub_agents=[writer, reviser]
)
