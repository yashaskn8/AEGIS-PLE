import unittest
from aegis.workflow_policy import WORKFLOW, validate


class WorkflowPolicy(unittest.TestCase):
    def test_exact_current_workflow(self):
        raw = WORKFLOW.read_text()
        self.assertEqual(validate(raw), validate("# formatting only\n" + raw))
        self.assertEqual(validate(raw)["promotion"], "BLOCKED")

    def test_original_yaml_parse_failure(self):
        raw = WORKFLOW.read_text().replace(
            "run: |\n          .venv/bin/python -m pip install --require-hashes --only-binary=:all: --no-deps -r requirements-ci.txt",
            "run: .venv/bin/python -m pip install --require-hashes --only-binary=:all: --no-deps -r requirements-ci.txt")
        self.assertNotEqual(raw, WORKFLOW.read_text())
        with self.assertRaisesRegex(ValueError, "malformed workflow"):
            validate(raw)

    def test_valid_yaml_with_changed_gate_rejected(self):
        raw = WORKFLOW.read_text()
        for old, new in (("run: .venv/bin/python -m aegis.ci", "run: echo ok"),
                         ("- name: Run fail-closed synthetic checks", "- name: Run fail-closed synthetic checks\n        if: false"),
                         ("persist-credentials: false", "persist-credentials: true"),
                         ("if-no-files-found: error", "if-no-files-found: warn")):
            changed = raw.replace(old, new)
            self.assertNotEqual(changed, raw)
            with self.assertRaises(ValueError):
                validate(changed)

    def test_duplicate_keys_and_aliases_rejected(self):
        raw = WORKFLOW.read_text()
        for changed in (raw + "\nname: overwritten\n", raw.replace("name: Synthetic CI", "name: &alias Synthetic CI"),
                        raw + "\nextra: !!str value\n"):
            with self.assertRaises(ValueError):
                validate(changed)
