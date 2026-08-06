"""Input validation — called from load_customer_documents before state is
written.

The check_inputs entry point runs everything in cost order: deterministic
checks first (free, pure), then the plausibility classifier (one flash
call), then Model Armor injection screening (free tier). If a service-backed
check is unavailable it logs and lets the upload continue.
"""

import logging
import os

from google import genai
from google.cloud import modelarmor_v1
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
    checks gate the decode, string checks next, the service-backed checks
    last so they only spend calls on inputs that already passed the free
    tier."""
    # Plain text that decodes as UTF-8? Must pass before decoding is safe.
    if not check_readable(cv_data, cv_mime) or not check_readable(jd_data, jd_mime):
        return InputVerdict(ok=False, reason="Files must be plain text (not PDF or Word).")

    cv_text = cv_data.decode("utf-8")
    jd_text = jd_data.decode("utf-8")

    # Same file uploaded twice? Then one slot is not what it claims to be.
    if not check_duplicates(cv_text, jd_text):
        return InputVerdict(ok=False, reason="Both files contain the same content.")

    # Each document between 200 and 50,000 characters (catches empty too).
    if not check_size(cv_text, jd_text):
        return InputVerdict(
            ok=False, reason="Each document must be roughly a paragraph to a few pages long."
        )

    # Is document A actually a CV, and B actually a job description?
    # One temperature-0 flash call; also catches the two files being swapped.
    verdict = await check_plausibility(cv_text, jd_text)
    if not (verdict.cv_ok and verdict.jd_ok):
        return InputVerdict(ok=False, reason=verdict.reason)

    # Model Armor screening: reject content that tries to steer the model
    # (prompt injection or jailbreak text hidden in a document).
    return await check_injection(cv_text, jd_text)


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


# Model Armor: screens the documents for prompt-injection and jailbreak
# content. The template (filters, thresholds) lives in GCP and can be
# tuned without code changes: projects/<project>/locations/europe-west4/
# templates/cv-agent-docs. The regional endpoint is required — the global
# one returns 404 for a regional template.
_ARMOR_LOCATION = "europe-west4"
_ARMOR_TEMPLATE_ID = "cv-agent-docs"


async def check_injection(cv_text: str, jd_text: str) -> InputVerdict:
    """Screen both documents with Model Armor: document content is data and
    must never be treated as instructions, so anything that reads as an
    attempt to steer the model is rejected before it reaches session state.

    If the screening service itself is unavailable, log a warning and let
    the upload continue — turning away every user because the checker is
    down would be worse than the risk it covers for a single-user app."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    try:
        client = modelarmor_v1.ModelArmorAsyncClient(
            client_options={"api_endpoint": f"modelarmor.{_ARMOR_LOCATION}.rep.googleapis.com"}
        )
        template = (
            f"projects/{project}/locations/{_ARMOR_LOCATION}/templates/{_ARMOR_TEMPLATE_ID}"
        )
        for label, text in (("CV", cv_text), ("job description", jd_text)):
            response = await client.sanitize_user_prompt(
                request=modelarmor_v1.SanitizeUserPromptRequest(
                    name=template,
                    user_prompt_data=modelarmor_v1.DataItem(text=text),
                )
            )
            state = response.sanitization_result.filter_match_state
            if state == modelarmor_v1.FilterMatchState.MATCH_FOUND:
                logger.warning(f"Model Armor flagged the {label}.")
                return InputVerdict(
                    ok=False,
                    reason=f"The {label} contains content that looks like an attempt "
                    "to manipulate the system.",
                )
        return InputVerdict(ok=True)
    except Exception as e:
        logger.warning(f"Injection screening unavailable, letting the upload continue: {e}")
        return InputVerdict(ok=True)
