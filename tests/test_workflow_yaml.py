# tests/test_workflow_yaml.py
"""Catch malformed workflows before a push makes GitHub reject them."""
from pathlib import Path

import pytest
import yaml

WORKFLOWS = sorted((Path(__file__).resolve().parents[1] / ".github/workflows").glob("*.yml"))


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda path: path.name)
def test_workflow_yaml_and_steps_are_well_formed(path):
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    assert isinstance(document.get("jobs"), dict) and document["jobs"]
    for job in document["jobs"].values():
        if "env" in job:
            assert isinstance(job["env"], dict)
        for step in job.get("steps", []):
            assert isinstance(step, dict)
            assert ("run" in step) != ("uses" in step)
            if "env" in step:
                assert isinstance(step["env"], dict)
            if "run" in step:
                assert isinstance(step["run"], str)
