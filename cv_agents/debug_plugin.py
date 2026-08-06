"""Opt-in diagnostics: logs the structure of the objects ADK hands to each
hook (contexts, requests, tools) so you can see what the framework passes
around and when.

Off by default and never registered unless CV_AGENT_DEBUG=1, so it adds
nothing to normal runs — the app code only carries the one-line
`*maybe_debug_plugins()` registration. Turn on with:

    CV_AGENT_DEBUG=1 uv run main.py
"""

import logging
import os

from google.adk.plugins import BasePlugin

logger = logging.getLogger("cv_agent.debug")


def _fields(obj, names) -> str:
    """A compact 'name=value' line for the attributes that exist; values
    truncated so a CV in state cannot flood the log."""
    parts = []
    for name in names:
        value = getattr(obj, name, "<absent>")
        text = repr(value)
        parts.append(f"{name}={text[:80]}{'…' if len(text) > 80 else ''}")
    return "  ".join(parts)


class DebugContextPlugin(BasePlugin):
    def __init__(self) -> None:
        super().__init__(name="debug_context")

    async def before_run_callback(self, *, invocation_context):
        ctx = invocation_context
        logger.info(
            f"RUN START  InvocationContext: "
            f"{_fields(ctx, ('invocation_id', 'app_name', 'user_id'))}  "
            f"agent={ctx.agent.name}  session={ctx.session.id}  "
            f"state_keys={list(ctx.session.state)}"
        )
        return None

    async def before_agent_callback(self, *, agent, callback_context):
        logger.info(
            f"AGENT      {agent.name}  CallbackContext: "
            f"{_fields(callback_context, ('invocation_id', 'agent_name'))}"
        )
        return None

    async def before_model_callback(self, *, callback_context, llm_request):
        logger.info(
            f"MODEL CALL by {callback_context.agent_name}  LlmRequest: "
            f"model={llm_request.model}  contents={len(llm_request.contents or [])} message(s)  "
            f"tools={list(llm_request.tools_dict or {})}"
        )
        return None

    async def before_tool_callback(self, *, tool, tool_args, tool_context):
        logger.info(
            f"TOOL CALL  {tool.name}({tool_args})  ToolContext: "
            f"{_fields(tool_context, ('invocation_id', 'agent_name'))}"
        )
        return None

    async def after_run_callback(self, *, invocation_context):
        ctx = invocation_context
        logger.info(
            f"RUN END    {ctx.invocation_id}  state_keys={list(ctx.session.state)}"
        )
        return None


def maybe_debug_plugins() -> list[BasePlugin]:
    """The one line the app code carries: empty list unless enabled."""
    if os.environ.get("CV_AGENT_DEBUG") == "1":
        logger.setLevel(logging.INFO)
        return [DebugContextPlugin()]
    return []
