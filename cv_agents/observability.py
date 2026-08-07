"""Single place that wires Langfuse tracing for an entry point.

Every process that runs the agents — the CLI (main.py), the HTTP API
(api/app.py), the experiment runner — must call init_langfuse() once,
BEFORE the agents run, or ADK spans are never emitted and the presenter's
judge metadata (customer_cv/job_description) has no span to attach to.

Historically this block was copy-pasted into main.py only, so the API path
ran untraced. Keep it here and call it from each entry point instead.
"""

import logging

from langfuse import get_client
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

from cv_agents.config import Config

logger = logging.getLogger(__name__)

_initialized = False


def init_langfuse() -> object:
    """Instrument ADK, export env, and return an authenticated Langfuse client.

    Idempotent: safe to call from multiple entry points / imports. Returns
    the Langfuse client so callers can flush() on short-lived processes.
    """
    global _initialized
    client = get_client()
    if _initialized:
        return client

    GoogleADKInstrumentor().instrument()
    Config().setup_environment()
    client = get_client()
    if client.auth_check():
        logger.info("Langfuse client is authenticated and ready")
    else:
        logger.warning(
            "Langfuse auth_check failed — traces will be dropped (check LANGFUSE_* in .env)"
        )
    _initialized = True
    return client
