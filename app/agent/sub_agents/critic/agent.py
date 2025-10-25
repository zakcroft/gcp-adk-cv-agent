from google.adk import Agent
from google.adk.tools import google_search

from . import prompt

critic_agent = Agent(
    model="gemini-2.5-flash",
    name="critic_agent",
    instruction=prompt.CRITIC_INSTRUCTION,
    tools=[google_search],
)
