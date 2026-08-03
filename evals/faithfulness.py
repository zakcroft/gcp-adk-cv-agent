"""faithfulness — is every fact in the produced CV grounded in the
customer's original CV? Catches invention (fake metrics, inflated titles).

Skips no-files items: there is no CV to be faithful to.
"""

from evals.common import judge, source_documents


async def faithfulness(*, input, output, expected_output=None, metadata=None, **kwargs):
    docs = source_documents(input)
    if docs is None:
        return []
    customer_cv, _ = docs
    return judge(
        "faithfulness",
        "judges/faithfulness",
        customer_cv=customer_cv,
        produced=str(output),
    )
