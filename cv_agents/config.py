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
        extra="ignore",
    )

    agent_settings: AgentModel = Field(default=AgentModel())
    app_name: str = "agents"
    CLOUD_PROJECT: str = Field(default="dev")
    CLOUD_LOCATION: str = Field(default="europe-west4")
    GENAI_USE_VERTEXAI: str = Field(default="1")
    API_KEY: str | None = Field(default="")

    # Langfuse observability (validation_alias bypasses the GOOGLE_ env prefix)
    LANGFUSE_PUBLIC_KEY: str | None = Field(default=None, validation_alias="LANGFUSE_PUBLIC_KEY")
    LANGFUSE_SECRET_KEY: str | None = Field(default=None, validation_alias="LANGFUSE_SECRET_KEY")
    LANGFUSE_BASE_URL: str = Field(
        default="https://cloud.langfuse.com", validation_alias="LANGFUSE_BASE_URL"
    )

    def setup_environment(self) -> None:
        """Export settings as the environment variables google-genai and Langfuse expect."""
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = self.GENAI_USE_VERTEXAI
        os.environ["GOOGLE_CLOUD_PROJECT"] = self.CLOUD_PROJECT
        os.environ["GOOGLE_CLOUD_LOCATION"] = self.CLOUD_LOCATION

        if self.GENAI_USE_VERTEXAI != "1":
            if not self.API_KEY:
                logger.warning("GOOGLE_GENAI_USE_VERTEXAI=0 but GOOGLE_API_KEY is not set")
            else:
                os.environ["GOOGLE_API_KEY"] = self.API_KEY

        if self.LANGFUSE_PUBLIC_KEY and self.LANGFUSE_SECRET_KEY:
            os.environ["LANGFUSE_PUBLIC_KEY"] = self.LANGFUSE_PUBLIC_KEY
            os.environ["LANGFUSE_SECRET_KEY"] = self.LANGFUSE_SECRET_KEY
            os.environ["LANGFUSE_BASE_URL"] = self.LANGFUSE_BASE_URL
        else:
            logger.info("Langfuse keys not set; skipping Langfuse configuration")
