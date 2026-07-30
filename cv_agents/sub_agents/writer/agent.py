from google.adk.agents import Agent, LoopAgent, SequentialAgent

from cv_agents.sub_agents.critic.agent import critic_agent
from cv_agents.sub_agents.presenter.agent import cv_presenter_agent
from cv_agents.sub_agents.reviser.agent import reviser_agent

from cv_agents.config import Config
from cv_agents.sub_agents.writer import prompt

configs = Config()


writer_agent = Agent(
    model=configs.agent_settings.model,
    name="writer_agent",
    description="Generates CV drafts tailored to job descriptions.",
    instruction=prompt.WRITER_INSTRUCTION,
    output_key="cv_draft",
)

# Loop agent for iterative CV refinement (Critic → Reviser)
# Terminates when the critic calls exit_loop or after max_iterations
reviser_loop_agent = LoopAgent(
    name="reviser_loop_agent",
    description="Iteratively critiques and revises the CV draft",
    sub_agents=[critic_agent, reviser_agent],
    max_iterations=3,
)

cv_writer_sequential_agent = SequentialAgent(
    name="cv_writer_sequential_agent",
    description="CV improvement workflow: Writer → Critic/Reviser loop → Presenter",
    sub_agents=[writer_agent, reviser_loop_agent, cv_presenter_agent],
)
