"""Output guardrails — called from cv_presenter_agent before the final CV
is emitted. These guard against model misbehaviour on valid input: the LLM
verifier in the loop can be argued with; these checks cannot.

Both return a list of problems (empty list = clean) rather than a verdict,
because the presenter's job on failure is to report specifics, not refuse.
"""

import re

from guardrails.limits import MAX_DOC_CHARS, MIN_DOC_CHARS

# Words that legitimately appear in a rewritten CV without appearing in the
# source: section headers and other structural vocabulary the writer adds.
STRUCTURAL_WORDS = {
    "professional",
    "summary",
    "experience",
    "employment",
    "education",
    "skills",
    "technical",
    "key",
    "achievements",
    "projects",
    "additional",
    "delivery",
    "notes",
    "fit",
    "note",
    "cv",
    "curriculum",
    "vitae",
}

# A token is "technical-shaped" when it looks like a technology or product
# name rather than ordinary prose: an internal capital (PostgreSQL), a
# digit (ES6), or joining punctuation (Next.js, CI/CD). A hyphen alone
# does NOT count — it joins ordinary English ("hands-on") far too often.
_TECHNICAL_SHAPE = re.compile(r"[A-Za-z][a-z]*[A-Z0-9]|[A-Za-z][\w]*[./+#][\w]")

_STRIP = ".,;:()!?'\"“”‘’[]"
# A capital after any of these ends is sentence case, not a name-like claim.
_SENTENCE_ENDS = (".", "!", "?", ":", "•", "-", "*", "–")


def _words(text: str) -> set[str]:
    """Every word in the text, lowercased, punctuation stripped, with
    hyphen/slash compounds also split into their parts."""
    words = set()
    for raw in text.split():
        bare = raw.lower().strip(_STRIP)
        if bare:
            words.add(bare)
            words.update(p for p in re.split(r"[-/]", bare) if p)
    return words


def check_grounding(cv_draft: str, customer_cv: str, job_description: str = "") -> list[str]:
    """Every technology or proper term in the draft must exist in the
    source CV or the job description. Returns the terms that do not —
    each is a claim the pipeline invented from nowhere.

    Scope note: JD vocabulary is allowed because tailoring legitimately
    uses the JD's role title and skills words (e.g. honest aspiration:
    "eager to develop SQL skills"). Whether a JD term is dishonestly
    claimed as EXPERIENCE is a question about meaning — that belongs to
    the loop verifier and the eval judges, not to code. (House style,
    enforced by the writer prompt: the CV never names the target
    company.)"""
    source_words = _words(customer_cv) | _words(job_description)
    source_lower = (customer_cv + "\n" + job_description).lower()
    violations = []

    for line in cv_draft.splitlines():
        sentence_start = True
        for raw in line.split():
            token = raw.strip(_STRIP)
            ends_sentence = raw.rstrip().endswith(_SENTENCE_ENDS) or raw in ("•", "-", "*", "–")
            if not token:
                sentence_start = sentence_start or ends_sentence
                continue
            bare = token.lower().strip(_STRIP)
            parts = [p for p in re.split(r"[-/]", bare) if p]
            known = (
                bare in source_words
                or bare in STRUCTURAL_WORDS
                or bare in source_lower
                or (parts and all(p in source_words or p in STRUCTURAL_WORDS for p in parts))
            )
            if not known:
                looks_technical = bool(_TECHNICAL_SHAPE.search(token))
                capitalised_mid_sentence = token[0].isupper() and not sentence_start
                if (looks_technical or capitalised_mid_sentence) and token not in violations:
                    violations.append(token)
            sentence_start = ends_sentence

    return violations


# The draft should look like a plain-text CV, not a chat reply or a
# markdown document. Size bounds are shared with the input gate — see
# guardrails/limits.py.
_MARKDOWN_ARTIFACTS = ("```", "## ", "**")


def check_format(cv_draft: str) -> list[str]:
    """Structural sanity of the final draft. Returns a list of problems."""
    problems = []
    n = len(cv_draft.strip())
    if n < MIN_DOC_CHARS:
        problems.append(f"draft is too short to be a CV ({n} chars)")
    if n > MAX_DOC_CHARS:
        problems.append(f"draft is implausibly long ({n} chars)")
    for artifact in _MARKDOWN_ARTIFACTS:
        if artifact in cv_draft:
            problems.append(f"draft contains markdown formatting ({artifact!r})")
    return problems
