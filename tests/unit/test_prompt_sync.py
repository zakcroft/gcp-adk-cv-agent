"""Guard against fallback drift: local prompt.py must match the Langfuse
`production` prompt version. Fails when someone promotes a new version in
the UI without syncing the local fallback (which would otherwise silently
serve stale instructions whenever Langfuse is down). Skips if Langfuse is
unreachable.
"""

import pytest

from cv_agents.config import Config

Config().setup_environment()

PAIRS = [
    ("agents/writer", "cv_agents.sub_agents.writer.prompt", "WRITER_INSTRUCTION"),
    ("agents/critic", "cv_agents.sub_agents.critic.prompt", "CRITIC_INSTRUCTION"),
    ("agents/reviser", "cv_agents.sub_agents.reviser.prompt", "REVISER_INSTRUCTION"),
    ("agents/verifier", "cv_agents.sub_agents.verifier.prompt", "VERIFIER_INSTRUCTION"),
]


def _production_prompt(name):
    from langfuse import get_client

    try:
        return get_client().get_prompt(name)
    except Exception as e:
        pytest.skip(f"Langfuse unreachable: {e}")


@pytest.mark.parametrize("prompt_name,module_path,var", PAIRS)
def test_local_fallback_matches_production(prompt_name, module_path, var):
    import importlib

    remote = _production_prompt(prompt_name)
    local = getattr(importlib.import_module(module_path), var)
    assert local == remote.prompt, (
        f"{module_path}.{var} has drifted from Langfuse '{prompt_name}' "
        f"v{remote.version} (production). Re-sync the local fallback."
    )
