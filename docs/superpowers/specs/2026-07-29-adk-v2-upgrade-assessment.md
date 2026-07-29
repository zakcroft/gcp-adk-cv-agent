# ADK 2.x Upgrade Assessment — cv-agent

**Date:** 2026-07-29
**Status:** Assessment only — no upgrade path chosen yet
**Current version:** google-adk 1.17.0 (locked in uv.lock)

## Is ADK 2.x stable?

Yes. ADK 2.0.0 went GA on **2026-05-19**; the 2.x line is at **2.5.0 (2026-07-16)** with no pre-release suffixes. Google is also still actively maintaining the 1.x line in parallel (1.36.2 released **2026-07-21**, after 2.5.0), so this is a maintained major-version fork, not an abandonment of 1.x. There is no forced urgency to move.

## What 2.0 changes

Headline: a **graph-based Workflow Runtime** replaces the 1.x hierarchical agent executor. Agents/tools/functions become nodes in a workflow graph. Official position: "designed to be compatible with agents developed with ADK 1.x," with these breaking changes:

| 2.x breaking change | Impact on cv-agent |
|---|---|
| Event schema gains `node_info` / `output` fields; 2.0 sessions readable by 1.28+ only | Low — we use `InMemorySessionService`, nothing persists session schema |
| `BaseAgent` → `BaseNode`; custom `_run_async_impl()` / `generate_content()` overrides silently bypassed | None — stock `LlmAgent` / `SequentialAgent` / `LoopAgent` only, no custom agent subclasses |
| Framework auto-retry: broad `except Exception:` in tools masks failures and disables retry/HITL | Low — audit the two tools in `cv_agents/tools.py` |
| Default model moved `gemini-2.5-flash` → `gemini-3-flash-preview` | None — every agent pins `model=` via `cv_agents/config.py` |

Unconfirmed: whether `LoopAgent` + `exit_loop` semantics are byte-for-byte unchanged under the graph engine. The loop-exit behaviour is the heart of the reviser pipeline — it is the first thing to verify in any spike.

## Project-specific risks

1. **Langfuse tracing may break (highest risk).** `openinference-instrumentation-google-adk` latest is **0.1.17** — the exact version we already run (released 2026-07-01, post-2.0-GA; dependency pin is only `google-adk>=1.2.1`, no advertised 2.x support). The instrumentor hooks Runner internals that the 2.0 graph engine replaced. Observability is a core feature of this project; silent trace loss is the most likely failure mode.
2. **Eval harness status undocumented.** No confirmation that `AgentEvaluator` + `.evalset.json` + `adk eval` survive unchanged in 2.x. The trajectory evals are the safety net for validating any migration — if they break, we lose the validation tool itself.

## Options

- **A. Two-step (recommended):** bump 1.17 → 1.36.x now (low risk, ~9 months of fixes; 1.28+ already understands the 2.0 event/session schema, so it is the designed stepping stone). Move to 2.x later, gated on openinference explicitly supporting ADK 2.
- **B. Spike 2.x on a branch:** `uv add 'google-adk[eval]>=2.5'` on a throwaway branch; run the chat app + both eval files; check Langfuse traces render. ~1 hour, answers both risk questions empirically. Note: nothing in 2.0 (graph workflows, HITL) is something this pipeline *needs* — SequentialAgent+LoopAgent already model it fine.
- **C. Full 2.x migration now:** only justified as a learning exercise; accepts being the canary for the instrumentor.

**Recommendation:** A, optionally with B for curiosity. The gate for 2.x is "Langfuse traces and `adk eval` verified working," not the version number.

## Sources

- https://pypi.org/project/google-adk/ (2.5.0 latest, stable)
- https://github.com/google/adk-python/releases (parallel 1.x/2.x release trains)
- https://adk.dev/2.0/ (ADK 2.0 overview)
- https://github.com/google/adk-docs/blob/main/docs/2.0/index.md (migration notes)
- https://dev.to/peytongreen_dev/google-adk-20-is-now-stable-workflow-runtimes-breaking-changes-and-how-to-migrate-4ah8
- https://pypi.org/project/openinference-instrumentation-google-adk/ (0.1.17, `google-adk>=1.2.1`)
