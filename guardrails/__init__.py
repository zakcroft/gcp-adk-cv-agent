"""Deterministic checks around the pipeline: plain input validation plus
model-behaviour guardrails. Pure functions, no ADK imports — callers wire
them in (tools, presenter, plugin)."""

from guardrails.inputs import check_inputs, check_readable, check_size

__all__ = ["check_inputs", "check_readable", "check_size"]
