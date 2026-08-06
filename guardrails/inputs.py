"""Input validation — called from load_customer_documents before state is
written.

Two tiers, in the order the tool runs them:
1. Deterministic checks (free, pure, no dependencies) — check_inputs.
2. LLM plausibility (one flash call, fails open) — check_plausibility.
"""

import logging

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Character counts, measured on the decoded str (not file bytes).
# Floor: smallest real CV in examples/cases is 375 chars, so 200 leaves
# headroom while rejecting junk. Ceiling: far above any real document;
# bounds token cost. Also catches empty strings (len 0 < MIN_CHARS).
MIN_CHARS = 200
MAX_CHARS = 50_000


def check_readable(data: bytes, mime_type: str) -> bool:
    """Bytes level: is this a plain-text file we can decode?"""
    if mime_type != "text/plain":
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def check_size(cv_text: str, jd_text: str) -> bool:
    """String level: each document big enough to be real, small enough
    to be sane."""
    for text in (cv_text, jd_text):
        n = len(text.strip())
        if n < MIN_CHARS or n > MAX_CHARS:
            return False
    return True


def check_duplicates(cv_text: str, jd_text: str) -> bool:
    """String level: two distinct documents — the same file uploaded twice
    means one of the slots is not what it claims to be."""
    if cv_text == jd_text:
        return False
    return True


class InputVerdict(BaseModel):
    ok: bool
    reason: str = Field(default="", description="User-facing reason when ok is False")


async def check_inputs(cv_data: bytes, cv_mime: str, jd_data: bytes, jd_mime: str) -> InputVerdict:
    """THE entry point: every input check in order, cheapest first — bytes
    checks gate the decode, string checks next, the LLM check last so it
    only spends a model call on inputs that already passed the free tier."""
    if not check_readable(cv_data, cv_mime) or not check_readable(jd_data, jd_mime):
        return InputVerdict(ok=False, reason="Files must be plain text (not PDF or Word).")

    cv_text = cv_data.decode("utf-8")
    jd_text = jd_data.decode("utf-8")

    if not check_duplicates(cv_text, jd_text):
        return InputVerdict(ok=False, reason="Both files contain the same content.")
    if not check_size(cv_text, jd_text):
        return InputVerdict(
            ok=False, reason="Each document must be roughly a paragraph to a few pages long."
        )

    verdict = await check_plausibility(cv_text, jd_text)
    if not (verdict.cv_ok and verdict.jd_ok):
        return InputVerdict(ok=False, reason=verdict.reason)
    return InputVerdict(ok=True)


# ---------------------------------------------------------------------------
# LLM tier. Everything below costs a model call and can fail — keep all
# deterministic checks above this line.
# ---------------------------------------------------------------------------

_MODEL = "gemini-2.5-flash"
# Classification needs the opening of each document, not the whole thing;
# truncation bounds cost, latency and injection surface.
_EXCERPT_CHARS = 1500

_PROMPT = """You are a strict document classifier. Two documents follow.

Document A should be a CV / resume: a document describing one person's own
work history, education or skills.
Document B should be a job description / advert: a document in which an
employer describes a role they want to fill.

Judge only what kind of document each one is — not quality, length or fit.

DOCUMENT A:
{cv_excerpt}

DOCUMENT B:
{jd_excerpt}
"""


class PlausibilityVerdict(BaseModel):
    cv_ok: bool = Field(description="Document A is plausibly a CV/resume")
    jd_ok: bool = Field(description="Document B is plausibly a job description")
    reason: str = Field(description="One short sentence explaining any failure; empty if both ok")


async def check_plausibility(cv_text: str, jd_text: str) -> PlausibilityVerdict:
    """Is this actually a CV, and that actually a JD? A question about
    meaning, which keyword heuristics answer badly — so one strict
    classification call, temperature 0, JSON out.

    FAILS OPEN: on any model/transport error we log and return both-ok — an
    unavailable quality gate must not take the product down with it."""
    try:
        client = genai.Client()
        response = await client.aio.models.generate_content(
            model=_MODEL,
            contents=_PROMPT.format(
                cv_excerpt=cv_text[:_EXCERPT_CHARS],
                jd_excerpt=jd_text[:_EXCERPT_CHARS],
            ),
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=PlausibilityVerdict,
            ),
        )
        verdict = response.parsed
        if verdict is None:
            raise ValueError("model returned no parseable verdict")
        return verdict
    except Exception as e:
        logger.warning(f"Plausibility check unavailable, failing open: {e}")
        return PlausibilityVerdict(cv_ok=True, jd_ok=True, reason="")
