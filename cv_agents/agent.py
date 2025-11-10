import logging
import warnings
from pathlib import Path

from google.adk import Agent
from google.adk.tools import FunctionTool
from google.adk.artifacts import InMemoryArtifactService
from google.genai import types

from cv_agents.sub_agents.writer.agent import cv_writer_agent
from cv_agents.config import Config
from cv_agents import prompt
from cv_agents import tools

warnings.filterwarnings("ignore", category=UserWarning, module=".*pydantic.*")

config = Config()
logger = logging.getLogger(__name__)


# Preload example files for local testing (in production, users upload via web UI)
async def load_example_files_to_artifacts(
    artifact_service: InMemoryArtifactService,
    app_name: str,
    user_id: str = "default_user",
    session_id: str = "default_session",
) -> None:
    project_root = Path(__file__).parent.parent
    examples_dir = project_root / "examples"

    example_files = [
        ("sample_cv.txt", "text/plain"),
        ("sample_job_description.txt", "text/plain"),
    ]

    for filename, mime_type in example_files:
        file_path = examples_dir / filename

        if not file_path.exists():
            logger.warning(f"Example file not found: {file_path}")
            continue

        try:
            with open(file_path, "rb") as f:
                file_content = f.read()

            file_part = types.Part.from_bytes(data=file_content, mime_type=mime_type)

            await artifact_service.save_artifact(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
                filename=filename,
                artifact=file_part,
            )

            logger.info(f"Loaded example file: {filename} ({len(file_content)} bytes)")

        except Exception as e:
            logger.error(f"Failed to load example file {filename}: {e}", exc_info=True)


load_docs_tool = FunctionTool(func=tools.load_customer_documents)
list_files_tool = FunctionTool(func=tools.list_uploaded_files)

root_agent = Agent(
    name=config.agent_settings.name,
    model=config.agent_settings.model,
    instruction=prompt.ROOT_INSTRUCTION,
    sub_agents=[cv_writer_agent],
    tools=[load_docs_tool, list_files_tool],
    output_key="final_cv",
)
