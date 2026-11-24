from dataclasses import replace
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import unittest
from zipfile import ZipFile

from aegis.distribution import build
from aegis.quality_evidence import Binding, digest, validate, verify_download

COMMIT = "654bf81d9bf75c995a744b86f5195dc88091b861"
ARCHIVE = Path("research/evidence") / (COMMIT + ".json")
STEPS = (
    "Set up job",
    "Run actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
    "Record candidate and interpreter",
    "Install hash-pinned loopback dependency",
    "Install hash-pinned static verification tools",
    "Lint syntax and undefined-name rules",
    "Strict type check typed arithmetic and evidence core",
    "Run fail-closed synthetic checks",
    "Run bounded synthetic experiment",
    "Compare dependency verification with full recomputation",
    "Generate and compare bounded verification policies",
    "Compare synthetic document reconciliation ablations",
    "Reproduce learned policy and measure fresh retention",
    "Compare scripted document repair and single attempt",
    "Analyze published baseline frontier",
    "Verify deterministic-first document route",
    "Analyze published discipline score matrix",
    "Check installed dependency consistency",
    "Verify checkout fingerprints and targeted mutation effectiveness",
    "Build and verify extracted educational distribution",
    "Archive verified educational distribution",
    "Post Run actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
    "Complete job",
)
BINDING = Binding(COMMIT, 45438357313, 138602262628, 105,
                  "19f2088cd463147569e4e46549ff3821fc3ef05c07b875ffc81e76cc95620a28", STEPS)


def record():
    return json.loads(ARCHIVE.read_text())


def wrap(inner, name="aegis-educational.zip"):
    buf = BytesIO()
    with ZipFile(buf, "w") as z:
        z.writestr(name, inner)
    return buf.getvalue()


class QualityEvidence(unittest.TestCase):
    def test_exact_historical_record(self):
        validate(record(), BINDING)
        for binding in (replace(BINDING, commit="a"*40), replace(BINDING, run=1),
                        replace(BINDING, tests=104), replace(BINDING, steps=STEPS[:-1])):
            with self.assertRaises(ValueError):
                validate(record(), binding)

    def test_modified_record_rejected(self):
        r = record()
        r["reports"]["synthetic checkout fingerprint"]["platform"] = "different"
        with self.assertRaises(ValueError):
            validate(r, BINDING)

    def test_structural_rejection_even_with_new_digest(self):
        for defect in ("skip", "step", "file", "mutation", "artifact", "promotion"):
            r = record()
            if defect == "skip":
                r["steps"][8]["conclusion"] = "skipped"
            elif defect == "step":
                r["steps"].pop(9)
            elif defect == "file":
                r["reports"]["synthetic checkout fingerprint"]["files"].pop("README.md")
            elif defect == "mutation":
                r["reports"]["targeted synthetic mutation gate"]["rows"][0]["mutant"]["errors"] = ["unrelated"]
            elif defect == "artifact":
                r["artifact"]["head_sha"] = "0"*40
            else:
                r["promotion"] = "ACCEPTED"
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                validate(r, replace(BINDING, record_sha256=digest(r)))

    def test_download_exact_and_tampered(self):
        files = {"example.txt": b"fictional"}
        inner = build(files, COMMIT)
        outer = wrap(inner)
        anchors = dict(commit=COMMIT, outer_sha=sha256(outer).hexdigest(),
                       inner_sha=sha256(inner).hexdigest(),
                       tree_digest=digest({k: {"sha256":sha256(v).hexdigest(), "bytes":len(v)}
                                           for k,v in files.items()}))
        self.assertEqual(verify_download(outer, **anchors)["files"], 1)
        for field in ("outer_sha", "inner_sha", "tree_digest"):
            with self.assertRaises(ValueError):
                verify_download(outer, **dict(anchors, **{field:"0"*64}))
        bad = wrap(inner, "unexpected.zip")
        with self.assertRaises(ValueError):
            verify_download(bad, **dict(anchors, outer_sha=sha256(bad).hexdigest()))

    def test_download_extra_inner_member(self):
        inner = BytesIO(build({"example.txt":b"fictional"}, COMMIT))
        with ZipFile(inner,"a") as z:
            z.writestr("unexpected.txt",b"other")
        outer = wrap(inner.getvalue())
        with self.assertRaises(ValueError):
            verify_download(outer, commit=COMMIT, outer_sha=sha256(outer).hexdigest(),
                            inner_sha=sha256(inner.getvalue()).hexdigest(), tree_digest="0"*64)

    def test_preflight_record_and_required_report(self):
        commit = "7850eb7544df48c28a7ab875b935bd9ec5ea7d04"
        r = json.loads((Path("research/evidence") / (commit + ".json")).read_text())
        steps = STEPS[:5] + ("Validate exact workflow policy",) + STEPS[5:]
        binding = Binding(commit, 45440048895, 138608320941, 114,
                          "ca564d79f31f4729f02779d19bf51f175c0df69bef6fd1caec40895270808832",
                          steps, "26b8924bfa56ffd79e89b6812aa2e46a274a716b4d79f36df5bd93ac2539907e")
        validate(r, binding)
        with self.assertRaises(ValueError):
            validate(r, replace(binding, workflow_policy_sha256=None))
        for defect in ("missing", "digest", "steps"):
            changed = json.loads(json.dumps(r))
            reports = changed["reports"]
            if defect == "missing":
                reports.pop("synthetic workflow preflight")
            elif defect == "digest":
                reports["synthetic workflow preflight"]["policy_sha256"] = "0"*64
            else:
                reports["synthetic workflow preflight"]["steps"] = 20
            with self.assertRaises(ValueError):
                validate(changed, replace(binding, record_sha256=digest(changed)))

    def test_required_resource_report_missing(self):
        # Deliberately defective fixture, not an observed CI record.
        r = record()
        step = "Measure isolated synthetic verification resources"
        r["steps"].insert(-2, {"name":step,"status":"completed","conclusion":"success"})
        steps = STEPS[:-2] + (step,) + STEPS[-2:]
        r["mandatory_steps"] = list(steps[4:-2])
        with self.assertRaisesRegex(ValueError, "missing or unexpected reports"):
            validate(r,replace(BINDING,steps=steps,record_sha256=digest(r)))
