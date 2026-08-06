"""Runtime guardrails — cross-cutting limits registered once on the Runner.

Unlike inputs/outputs these are not pure functions: they hold state across
the run, so they live in an ADK Plugin."""


# TODO: per-run LLM-call ceiling — before_model_callback counts calls and
# short-circuits when over budget.
# class GuardrailsPlugin(BasePlugin): ...

# TODO: per-LLM-call timeout — not a callback; set http_options timeout on
# the Gemini client so a hung connection raises and backoff catches it.

# LATER: prompt-injection screening (Model Armor) would hook in here too.
