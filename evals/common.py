"""Shared plumbing for the eval suite: judge invocation and source-document
resolution.
"""

import json
import logging
from pathlib import Path

from langfuse import Evaluation, get_client

from cv_agents.config import Config

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
config = Config()

# Judges use the lite model: cheaper, and halves contention on the shared
# Vertex quota that 429s the pipeline's own calls.
JUDGE_MODEL = "gemini-2.5-flash-lite"


def judge(score_name: str, prompt_name: str, **variables) -> Evaluation:
    """Run one LLM judge: fetch its prompt (label `production`), call Gemini,
    parse the JSON verdict. Score records the judge prompt version."""
    from google import genai

    prompt = get_client().get_prompt(prompt_name)
    # Keep a reference: an unreferenced Client can be garbage-collected
    # mid-call, closing its connection pool ("client has been closed").
    client = genai.Client()
    response = None
    for attempt, delay in enumerate((20, 45, 90, 180, 300, None)):
        try:
            response = client.models.generate_content(
                model=JUDGE_MODEL,
                contents=prompt.compile(**variables),
                config={"response_mime_type": "application/json"},
            )
            break
        except Exception as e:
            if "429" not in str(e) or delay is None:
                raise
            print(f"  [{score_name}] 429 (attempt {attempt + 1}); retrying in {delay}s...")
            import time

            time.sleep(delay)
    verdict = json.loads(response.text)
    print(f"  [{score_name}] {float(verdict['score']):.2f} — {verdict.get('reason', '')[:90]}")
    return Evaluation(
        name=score_name,
        value=float(verdict["score"]),
        comment=verdict.get("reason", ""),
        metadata={"judge_prompt_version": prompt.version},
    )


def source_documents(item_input) -> tuple[str, str] | None:
    """Resolve (customer_cv, job_description) for a dataset item, or None for
    no-files items. Plain-string inputs are the senior-match case; dict inputs
    carry a `case` id resolving to examples/cases/<case>/{cv,jd}.txt."""
    if isinstance(item_input, str):
        case_dir = PROJECT_ROOT / "examples" / "cases" / "senior-match"
        return ((case_dir / "cv.txt").read_text(), (case_dir / "jd.txt").read_text())
    case = item_input.get("case")
    if case is None:
        return None
    case_dir = PROJECT_ROOT / "examples" / "cases" / case
    return ((case_dir / "cv.txt").read_text(), (case_dir / "jd.txt").read_text())


