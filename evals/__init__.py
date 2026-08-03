"""Dev-side evaluation suite: one judge per failure mode, run by
scripts/run_dataset_experiment.py over the regression-cases dataset.

Judge prompts live in Langfuse Prompt Management (label `production`);
every score records which prompt version judged it.
"""

from evals.completeness import completeness
from evals.correctness import correctness
from evals.faithfulness import faithfulness
from evals.hallucination import hallucination
from evals.tailoring import tailoring

ALL_EVALUATORS = [correctness, faithfulness, hallucination, completeness, tailoring]
