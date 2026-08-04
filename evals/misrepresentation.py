"""misrepresentation — is the person in the produced CV the same person at
the same level as in the original? Catches identity re-levelling in either
direction: a thin CV promoted senior-ward, or a strong CV flattened to fit
a junior role (the Elena case, 2026-08-03).

Skips no-files items.
"""

from evals.common import judge, source_documents


async def misrepresentation(*, input, output, expected_output=None, metadata=None, **kwargs):
    docs = source_documents(input)
    if docs is None:
        return []
    customer_cv, _ = docs
    return judge(
        "misrepresentation",
        "judges/misrepresentation",
        customer_cv=customer_cv,
        produced=str(output),
    )
