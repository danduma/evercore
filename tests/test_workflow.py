import tempfile
import unittest
from pathlib import Path

import yaml

from evercore.workflow import WorkflowLoader, WorkflowValidationError, WorkflowValidator


class WorkflowTests(unittest.TestCase):
    def test_validator_rejects_missing_initial_stage(self):
        payload = {
            "key": "bad",
            "version": "1.0.0",
            "initial_stage": "missing",
            "stages": [{"id": "queued", "executor": "x"}],
        }
        validator = WorkflowValidator()
        with self.assertRaises(WorkflowValidationError):
            validator.validate(payload)

    def test_validator_rejects_unknown_transition_target(self):
        payload = {
            "key": "bad",
            "version": "1.0.0",
            "initial_stage": "queued",
            "stages": [
                {
                    "id": "queued",
                    "executor": "x",
                    "transitions": [{"target": "does-not-exist"}],
                }
            ],
        }
        validator = WorkflowValidator()
        with self.assertRaises(WorkflowValidationError):
            validator.validate(payload)

    def test_loader_injects_workflow_key_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            workflow_dir = Path(tmp_dir)
            workflow_file = workflow_dir / "custom.yaml"
            payload = {
                "version": "1.0.0",
                "initial_stage": "queued",
                "stages": [{"id": "queued", "executor": "x"}],
            }
            workflow_file.write_text(yaml.safe_dump(payload), encoding="utf-8")
            loader = WorkflowLoader(workflow_dir)
            loaded = loader.load("custom")

        self.assertEqual(loaded.key, "custom")
        self.assertEqual(loaded.stage_by_id("queued").id, "queued")

    def test_loader_missing_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            loader = WorkflowLoader(tmp_dir)
            with self.assertRaises(FileNotFoundError):
                loader.load("missing")


if __name__ == "__main__":
    unittest.main()

