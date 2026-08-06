"""Output guardrails — called from cv_presenter_agent before the final CV
is emitted. Guard against model misbehaviour on valid input."""


# TODO: grounding gate — technology/term diff of cv_draft vs customer_cv;
# any term in the output that is not in the source CV is a violation.
# def check_grounding(cv_draft: str, customer_cv: str) -> bool: ...

# TODO: format check — plain-text CV, expected sections present, sane length.
# def check_format(cv_draft: str) -> bool: ...
