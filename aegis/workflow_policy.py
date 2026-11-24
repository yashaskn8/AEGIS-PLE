"""Repository-owned exact CI workflow preflight; run before committing edits.

The digest binds parsed workflow semantics, not formatting. It cannot replace
an independently protected policy or detect a workflow that never starts remotely.
"""
import hashlib
import json
from pathlib import Path
import re

import yaml

WORKFLOW = Path(".github/workflows/ci.yml")
EXPECTED = "1b913e6563c434cdd1b0a5a969123c45e5b87dfc62a07e8e4b6013cd726670f9"
MAX_BYTES = 32768


class UniqueLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        pairs = self.construct_pairs(node, deep=deep)
        result = {}
        for key, value in pairs:
            if type(key) is not str or key in result:
                raise ValueError("duplicate or non-string YAML key")
            result[key] = value
        return result


# GitHub's on key must remain a string; preserve actual booleans and nulls.
UniqueLoader.yaml_implicit_resolvers = {
    key: [(tag, pattern) for tag, pattern in resolvers
          if tag != "tag:yaml.org,2002:bool"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
UniqueLoader.add_implicit_resolver("tag:yaml.org,2002:bool",
                                   re.compile(r"^(?:true|false|True|False|TRUE|FALSE)$"),
                                   list("tTfF"))


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
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validate(raw):
    value = parse(raw)
    actual = fingerprint(value)
    if actual != EXPECTED:
        raise ValueError("workflow differs from the mandatory policy")
    return {"scope":"synthetic workflow preflight", "policy_sha256":actual,
            "steps":len(value["jobs"]["verification"]["steps"]), "promotion":"BLOCKED"}


if __name__ == "__main__":
    print(json.dumps(validate(WORKFLOW.read_text()), sort_keys=True))
