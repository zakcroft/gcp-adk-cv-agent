"""Fetch agent instructions from Langfuse Prompt Management.

Instructions are edited/versioned in the Langfuse UI (label `production`);
the local prompt.py text is the fallback so the app still runs when
Langfuse is down. Fetched at import time — restart the app to pick up a
new version (same rule as local prompt edits).
"""

import logging

from cv_agents.config import Config

logger = logging.getLogger(__name__)


def fetch_instruction(name: str, fallback: str) -> str:
    try:
        Config().setup_environment()
        from langfuse import get_client

        prompt = get_client().get_prompt(name)
        logger.info(f"Loaded instruction '{name}' v{prompt.version} from Langfuse")
        return prompt.prompt
    except Exception as e:
        logger.warning(f"Langfuse prompt '{name}' unavailable ({e}); using local fallback")
        return fallback
