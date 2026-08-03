"""Route all pytest trace output to its own Langfuse environment so live
evaluators (which watch `default`) never judge test traffic. Importing
cv_agents initialises the Langfuse client (prompt fetching), so even unit
tests emit traces — this must be set before any test module imports.
"""

import os

os.environ.setdefault("LANGFUSE_TRACING_ENVIRONMENT", "pytest")
