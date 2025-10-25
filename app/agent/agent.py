import logging
import warnings
from google.adk import Agent

from app.agent.sub_agents.writer.agent import cv_writer_agent
from app.agent.config import Config

from . import prompt


warnings.filterwarnings("ignore", category=UserWarning, module=".*pydantic.*")

config = Config()

logger = logging.getLogger(__name__)


root_agent = Agent(
    name=config.agent_settings.name,
    model=config.agent_settings.model,
    instruction=prompt.ROOT_INSTRUCTION,
    sub_agents=[
        cv_writer_agent,
    ],
    output_key="final_cv",
)
