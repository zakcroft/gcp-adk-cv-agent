from google.adk.agents import Agent, LoopAgent, SequentialAgent
from google.adk.tools import google_search

from app.agent.sub_agents.critic.agent import critic_agent
from app.agent.sub_agents.reviser.agent import reviser_agent

from app.agent.config import Config

configs = Config()


writer = Agent(
    model=configs.agent_settings.model,
    name="writer",
    description="Writes a technical blog post.",
    instruction="""
    You are an expert technical writer, crafting articles for a sophisticated audience similar to that of 'Towards Data Science' and 'freeCodeCamp'.
    Your task is to write a high-quality, in-depth technical blog post based on the provided outline and codebase summary.
    The article must be well-written, authoritative, and engaging for a technical audience.
    - Assume your readers are familiar with programming concepts and software development.
    - Dive deep into the technical details. Explain the 'how' and 'why' behind the code.
    - Use code snippets extensively to illustrate your points.
    - Use Google Search to find relevant information and examples to support your writing.
    - The codebase context will be available in the `codebase_context` state key.
    The final output must be a complete blog post in Markdown format. Do not wrap the output in a code block.
    """,
    tools=[google_search],
    output_key="initial_draft",
)

# TODO - add a termination condition
reviser = LoopAgent(
    name="reviser",
    description="A CV reviser",
    sub_agents=[critic_agent, reviser_agent],
    max_iterations=3,
)

cv_writer_agent = SequentialAgent(
    name="cv_writer_agent", description="Cv writer agent", sub_agents=[writer, reviser]
)
