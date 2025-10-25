import os
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, Field


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class AgentModel(BaseModel):
    """Agent model settings."""

    name: str = Field(default="cv_agent")
    model: str = Field(default="gemini-2.5-flash")


class Config(BaseSettings):
    """Configuration settings for the customer service agent."""

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../.env"),
        env_prefix="GOOGLE_",
        case_sensitive=True,
    )

    agent_settings: AgentModel = Field(default=AgentModel())
    app_name: str = "cv_agent_app"
    CLOUD_PROJECT: str = Field(default="dev")
    CLOUD_LOCATION: str = Field(default="europe-west2")
    STAGING_BUCKET: str | None = Field(default="staging-bucket")
    GENAI_USE_VERTEXAI: str = Field(default="1")
    API_KEY: str | None = Field(default="")
