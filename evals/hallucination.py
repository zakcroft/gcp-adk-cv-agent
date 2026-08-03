"""hallucination — implied claims beyond the original CV (framing that
suggests seniority/scale/expertise the original never states). Cross-checks
faithfulness from a different angle; disagreement between them is signal.

Skips no-files items.
"""

from evals.common import judge, source_documents


async def hallucination(*, input, output, expected_output=None, metadata=None, **kwargs):
    docs = source_documents(input)
    if docs is None:
        return []
    customer_cv, _ = docs
    return judge(
        "hallucination",
        "hallucination-judge",
        customer_cv=customer_cv,
        produced=str(output),
    )
