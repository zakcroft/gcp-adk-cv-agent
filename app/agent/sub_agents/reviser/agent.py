from google.adk import Agent

from . import prompt

reviser_agent = Agent(
    model="gemini-2.5-flash",
    name="reviser_agent",
    instruction=prompt.INSTRUCTION,
)
