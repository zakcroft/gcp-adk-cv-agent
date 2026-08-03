"""tailoring — does the produced CV address the job description's key
requirements with grounded content? Includes the rounded rule: skills
outside the JD are kept, never penalised, as long as they are not the main
focus.

Skips no-files items.
"""

from evals.common import judge, source_documents


async def tailoring(*, input, output, expected_output=None, metadata=None, **kwargs):
    docs = source_documents(input)
    if docs is None:
        return []
    customer_cv, job_description = docs
    return judge(
        "tailoring",
        "judges/tailoring",
        customer_cv=customer_cv,
        job_description=job_description,
        produced=str(output),
    )
