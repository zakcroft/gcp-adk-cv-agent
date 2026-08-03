"""completeness — was anything material from the original CV silently
dropped? The reverse direction of faithfulness: nothing false gets in,
nothing true falls out.

Skips no-files items.
"""

from evals.common import judge, source_documents


async def completeness(*, input, output, expected_output=None, metadata=None, **kwargs):
    docs = source_documents(input)
    if docs is None:
        return []
    customer_cv, _ = docs
    return judge(
        "completeness",
        "completeness-judge",
        customer_cv=customer_cv,
        produced=str(output),
    )
