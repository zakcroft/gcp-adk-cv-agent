import os
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, Field


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


GEMINI_2_5_pro = "gemini-2.5-pro"
GEMINI_2_5_flash = "gemini-2.5-flash"


class AgentModel(BaseModel):
    """Agent model settings."""

    name: str = Field(default="cv_agent_app")
    model: str = Field(default=GEMINI_2_5_flash)


class Config(BaseSettings):
    """Configuration settings for the CV agent."""

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.env"),
        env_prefix="GOOGLE_",
        case_sensitive=True,
    )

    agent_settings: AgentModel = Field(default=AgentModel())
    app_name: str = "agents"
    CLOUD_PROJECT: str = Field(default="dev")
    CLOUD_LOCATION: str = Field(default="europe-west4")
    GENAI_USE_VERTEXAI: str = Field(default="1")
    API_KEY: str | None = Field(default="")
