"""resolve_item maps a dataset item's input to (message, artifacts to preload)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.run_dataset_experiment import resolve_item


def test_case_item_loads_its_own_documents():
    message, artifacts = resolve_item({"message": "improve my cv", "case": "sparse-cv"})
    assert message == "improve my cv"
    names = [name for name, _ in artifacts]
    assert names == ["sample_cv.txt", "sample_job_description.txt"]
    assert b"Tom Okafor" in artifacts[0][1]


def test_no_files_item_preloads_nothing():
    message, artifacts = resolve_item({"message": "What files?", "case": None})
    assert message == "What files?"
    assert artifacts == []


def test_legacy_string_input_uses_default_documents():
    message, artifacts = resolve_item("make a cv for me")
    assert message == "make a cv for me"
    assert len(artifacts) == 2
    assert b"John Smith" in artifacts[0][1]
