import asyncio
import logging
import warnings
from datetime import datetime
from pathlib import Path

from google.adk.runners import Runner
from google.adk.artifacts import InMemoryArtifactService
from google.adk.sessions import InMemorySessionService
from google.genai import types

from cv_agents.agent import root_agent
from guardrails.runtime import GuardrailsPlugin
from cv_agents.debug_plugin import maybe_debug_plugins
from cv_agents.config import Config

from langfuse import get_client

from openinference.instrumentation.google_adk import GoogleADKInstrumentor

GoogleADKInstrumentor().instrument()

warnings.filterwarnings("ignore", category=UserWarning, module=".*pydantic.*")
logger = logging.getLogger(__name__)
config = Config()

# Export Vertex AI / Langfuse settings from .env into the environment
config.setup_environment()

USER_ID = "user_1"
# Unique per run so each chat groups as its own session in Langfuse
SESSION_ID = f"session_{datetime.now():%Y%m%d_%H%M%S}"

langfuse = get_client()

# Verify connection
if langfuse.auth_check():
    print("Langfuse client is authenticated and ready!")
else:
    print("Authentication failed. Please check your credentials and host.")


async def load_example_files_to_artifacts(
    artifact_service: InMemoryArtifactService,
    app_name: str,
    user_id: str = "default_user",
    session_id: str = "default_session",
) -> None:
    # Documents come from the senior-match case (examples/cases/ is the single
    # source of truth); artifact names stay sample_* — the tools expect them.
    case_dir = Path(__file__).parent / "examples" / "cases" / "senior-match"
    example_files = [
        ("sample_cv.txt", "cv.txt", "text/plain"),
        ("sample_job_description.txt", "jd.txt", "text/plain"),
    ]

    for filename, case_file, mime_type in example_files:
        path = case_dir / case_file
        if not path.exists():
            logger.warning(f"Missing example file: {path}")
            continue

        content = path.read_bytes()
        part = types.Part.from_bytes(data=content, mime_type=mime_type)
        await artifact_service.save_artifact(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            filename=filename,
            artifact=part,
        )
        logger.info(f"Loaded {filename} ({len(content)} bytes)")


# Agent Interaction (Async)
async def chat_loop(runner):
    while True:
        user_input = input("You: ")
        if user_input.lower() in {"exit", "quit"}:
            break

        new_message = types.Content(role="user", parts=[types.Part(text=user_input)])

        print("\n--- Processing your message ---")
        final_response_text = "No final text response captured."
        try:
            # Use run_async
            async for event in runner.run_async(
                user_id=USER_ID, session_id=SESSION_ID, new_message=new_message
            ):
                print(f"Event ID: {event.id}, Author: {event.author}")

                # --- Check for specific parts FIRST ---
                has_specific_part = False
                if event.content and event.content.parts:
                    for part in event.content.parts:  # Iterate through all parts
                        if part.executable_code:
                            # Access the actual code string via .code
                            print(
                                f"  Debug: Agent generated code:\n```python\n{part.executable_code.code}\n```"
                            )
                            has_specific_part = True
                        elif part.code_execution_result:
                            # Access outcome and output correctly
                            print(
                                f"  Debug: Code Execution Result: {part.code_execution_result.outcome} - Output:\n{part.code_execution_result.output}"
                            )
                            has_specific_part = True
                        # Also print any text parts found in any event for debugging
                        elif part.text and not part.text.isspace():
                            print(f"  Text: '{part.text.strip()}'")
                            # Do not set has_specific_part=True here, as we want the final response logic below

                # --- Check for final response AFTER specific parts ---
                # Only consider it final if it doesn't have the specific code parts we just handled
                if not has_specific_part and event.is_final_response():
                    if event.content and event.content.parts and event.content.parts[0].text:
                        final_response_text = event.content.parts[0].text.strip()
                        print(f"final_response_text: {final_response_text}")
                    else:
                        print("final_response_text: [No text content in final event]")

        except Exception as e:
            print(f"ERROR during agent run: {e}")
        print("-" * 30 + "\n")


async def main():
    session_service = InMemorySessionService()
    artifact_service = InMemoryArtifactService()

    await session_service.create_session(
        app_name=config.app_name,
        user_id=USER_ID,
        session_id=SESSION_ID,
    )

    await load_example_files_to_artifacts(
        artifact_service=artifact_service,
        app_name=config.app_name,
        user_id=USER_ID,
        session_id=SESSION_ID,
    )

    runner = Runner(
        agent=root_agent,
        app_name=config.app_name,
        artifact_service=artifact_service,
        session_service=session_service,
        plugins=[GuardrailsPlugin(), *maybe_debug_plugins()],
    )

    print("\n" + "=" * 60)
    print("CV Agent - Interactive Chat")
    print("=" * 60)
    print("Files loaded")
    print(
        await artifact_service.list_artifact_keys(
            app_name=config.app_name,
            user_id=USER_ID,
            session_id=SESSION_ID,
        )
    )
    print("Type 'exit' or 'quit' to end the conversation")
    print("=" * 60 + "\n")

    await chat_loop(runner)

    # Log final Session state
    print("\n=== Final Session State ===")
    session = await session_service.get_session(
        app_name=config.app_name, user_id=USER_ID, session_id=SESSION_ID
    )
    for key, value in session.state.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
