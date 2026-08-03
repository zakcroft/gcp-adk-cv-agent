"""correctness — is the output as good as the item's expected output?

Dev-only by nature: live requests have no expected output to compare with.
"""

from evals.common import judge


async def correctness(*, input, output, expected_output, metadata=None, **kwargs):
    if not expected_output:
        return []
    return judge(
        "correctness",
        "judges/correctness",
        query=str(input),
        expected=expected_output,
        produced=str(output),
    )
