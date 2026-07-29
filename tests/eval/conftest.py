"""Instrument eval runs so they appear as traces in Langfuse (user: test_user)."""

import pytest

from cv_agents.config import Config

Config().setup_environment()

from langfuse import get_client
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

# Initialize the Langfuse client BEFORE any agent runs: it registers the OTel
# exporter that the instrumentor's spans are delivered through
langfuse = get_client()
GoogleADKInstrumentor().instrument()


@pytest.fixture(scope="session", autouse=True)
def flush_langfuse():
    yield
    langfuse.flush()
