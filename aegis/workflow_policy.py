"""Repository-owned exact CI workflow preflight; run before committing edits.

The digest binds parsed workflow semantics, not formatting. It cannot replace
an independently protected policy or detect a workflow that never starts remotely.
"""
import hashlib
import json
from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/ci.yml")
EXPECTED = "26b8924bfa56ffd79e89b6812aa2e46a274a716b4d79f36df5bd93ac2539907e"
MAX_BYTES = 32768


class UniqueLoader(yaml.BaseLoader):
    def construct_mapping(self, node, deep=False):
        pairs = self.construct_pairs(node, deep=deep)
        result = {}
        for key, value in pairs:
            if type(key) is not str or key in result:
                raise ValueError("duplicate or non-string YAML key")
            result[key] = value
        return result


def parse(raw):
    if type(raw) is not str or len(raw.encode()) > MAX_BYTES:
        raise ValueError("invalid workflow size")
    try:
        if any(isinstance(t, (yaml.tokens.AnchorToken, yaml.tokens.AliasToken, yaml.tokens.TagToken))
               for t in yaml.scan(raw)):
            raise ValueError("workflow aliases, anchors and explicit tags are unsupported")
        value = yaml.load(raw, Loader=UniqueLoader)
    except (yaml.YAMLError, RecursionError) as exc:
        raise ValueError("malformed workflow") from exc
    if type(value) is not dict:
        raise ValueError("workflow must be a mapping")
    return value


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate(raw):
    value = parse(raw)
    actual = fingerprint(value)
    if actual != EXPECTED:
        raise ValueError("workflow differs from the mandatory policy")
    return {"scope":"synthetic workflow preflight", "policy_sha256":actual,
            "steps":len(value["jobs"]["verification"]["steps"]), "promotion":"BLOCKED"}


if __name__ == "__main__":
    print(json.dumps(validate(WORKFLOW.read_text()), sort_keys=True))
