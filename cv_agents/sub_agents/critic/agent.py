from google.adk import Agent
from google.adk.tools import FunctionTool

from . import prompt
from cv_agents.config import Config
import cv_agents.tools as tools

configs = Config()

load_docs_tool = FunctionTool(func=tools.load_customer_documents)
list_files_tool = FunctionTool(func=tools.list_uploaded_files)

critic_agent = Agent(
    model=configs.agent_settings.model,
    name="critic_agent",
    instruction=prompt.CRITIC_INSTRUCTION,
    tools=[load_docs_tool, list_files_tool],
    output_key="cv_criticism",
)
