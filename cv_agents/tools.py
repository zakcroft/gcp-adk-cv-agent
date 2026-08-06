"""Tools for the CV improvement agent."""

from typing import List
from pydantic import BaseModel, Field
import logging

from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import ToolContext
from google.genai import types

from guardrails import check_inputs

logger = logging.getLogger(__name__)


class DocumentsResult(BaseModel):
    customer_cv: str = Field(description="The full text of the customer's CV")
    job_description: str = Field(description="The full text of the job description")
    cv_filename: str = Field(description="Name of the CV file")
    job_filename: str = Field(description="Name of the job description file")
    status: str = Field(description="Status of the operation: 'success' or 'error'")
    error: str = Field(default="", description="Error message if status is 'error'")
    uploaded_files: List[str] = Field(default_factory=list, description="List of uploaded files")


class FilesListResult(BaseModel):
    files: List[str] = Field(description="List of uploaded filenames")
    count: int = Field(description="Number of files")
    status: str = Field(description="Status of the operation: 'success' or 'error'")
    error: str = Field(default="", description="Error message if status is 'error'")


# Save generated output files (PDFs, improved CVs, etc.) for the user to download
async def save_generated_file(
    context: CallbackContext,
    filename: str,
    content_bytes: bytes,
    mime_type: str = "application/pdf",
):
    file_part = types.Part.from_bytes(data=content_bytes, mime_type=mime_type)
    version = await context.save_artifact(filename=filename, artifact=file_part)
    logger.info(f"Saved file '{filename}' (version {version})")
    return version


# Load the CV and job description files
async def load_customer_documents(tool_context: ToolContext) -> dict:
    try:
        artifacts = await tool_context.list_artifacts()
        logger.info(f"Found {len(artifacts)} files: {artifacts}")

        cv_filename = artifacts[0]
        job_filename = artifacts[1]

        cv_artifact_part = await tool_context.load_artifact(cv_filename)
        job_artifact_part = await tool_context.load_artifact(job_filename)
        cv_part = cv_artifact_part.inline_data if cv_artifact_part else None
        job_part = job_artifact_part.inline_data if job_artifact_part else None

        if cv_part is None or job_part is None:
            logger.warning(f"Could not read '{cv_filename}' and/or '{job_filename}'.")
            return DocumentsResult(
                customer_cv="",
                job_description="",
                cv_filename="",
                job_filename="",
                error="Could not read the uploaded files. Please upload them again.",
                status="error",
            ).model_dump()

        # Guardrail: validate BEFORE anything is written to state
        if not check_inputs(cv_part.data, cv_part.mime_type, job_part.data, job_part.mime_type):
            logger.warning("Input validation failed for uploaded files.")
            return DocumentsResult(
                customer_cv="",
                job_description="",
                cv_filename="",
                job_filename="",
                error=(
                    "The uploaded files failed validation. Please upload your CV and the "
                    "job description as plain text files of a reasonable length."
                ),
                status="error",
            ).model_dump()

        cv_text = cv_part.data.decode("utf-8")
        job_text = job_part.data.decode("utf-8")
        logger.info(f"Loaded CV ({len(cv_text)} chars) and job description ({len(job_text)} chars)")

        # Persist to session state so sub-agent instructions can inject them
        # via {customer_cv} / {job_description} placeholders
        tool_context.state["customer_cv"] = cv_text
        tool_context.state["job_description"] = job_text

        # model_dump() so the result serializes cleanly in traces (Langfuse
        # renders Pydantic objects as "<not serializable>")
        return DocumentsResult(
            customer_cv=cv_text,
            job_description=job_text,
            cv_filename=cv_filename,
            job_filename=job_filename,
            status="success",
        ).model_dump()

    except UnicodeDecodeError as e:
        logger.error(f"Failed to decode file as UTF-8: {e}")
        return DocumentsResult(
            customer_cv="",
            job_description="",
            cv_filename="",
            job_filename="",
            error="Failed to read files. Please ensure they are text files (not PDFs or Word documents).",
            status="error",
        ).model_dump()
    except Exception as e:
        logger.error(f"Failed to load documents: {e}", exc_info=True)
        return DocumentsResult(
            customer_cv="",
            job_description="",
            cv_filename="",
            job_filename="",
            error=f"Failed to load documents: {str(e)}",
            status="error",
        ).model_dump()


# List all available files
async def list_uploaded_files(tool_context: ToolContext) -> dict:
    try:
        artifacts = await tool_context.list_artifacts()
        return FilesListResult(files=artifacts, count=len(artifacts), status="success").model_dump()
    except Exception as e:
        logger.error(f"Failed to list files: {e}", exc_info=True)
        return FilesListResult(
            error=f"Failed to list files: {str(e)}", status="error", files=[], count=0
        ).model_dump()
