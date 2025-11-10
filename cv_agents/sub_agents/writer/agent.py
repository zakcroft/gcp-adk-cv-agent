from google.adk.agents import Agent, LoopAgent, SequentialAgent

from cv_agents.sub_agents.critic.agent import critic_agent
from cv_agents.sub_agents.reviser.agent import reviser_agent

from cv_agents.config import Config
from cv_agents.sub_agents.writer import prompt

configs = Config()


writer = Agent(
    model=configs.agent_settings.model,
    name="writer",
    description="Generates CV drafts tailored to job descriptions.",
    instruction=prompt.WRITER_INSTRUCTION,
    output_key="initial_draft",
)

# Loop agent for iterative CV refinement (Critic → Reviser)
# Terminates when reviser sets validated=true or after max_iterations
reviser = LoopAgent(
    name="reviser",
    description="Iteratively critiques and revises the CV draft",
    sub_agents=[critic_agent, reviser_agent],
    max_iterations=3,
)

cv_writer_agent = SequentialAgent(
    name="cv_writer_agent",
    description="CV improvement workflow: Writer → Critic → Reviser loop",
    sub_agents=[writer, reviser],
)
