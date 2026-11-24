"""Revision-aware reconciliation of bounded fictional project inventory records.

A trusted manifest declares exactly which document families and revisions
are allowed, and which keys are required. Content cannot grant itself authority.
No physical design, professional approval, or official benchmark data is used.
"""
from dataclasses import dataclass
from hashlib import sha256
import re
import csv
from io import StringIO

from .firewall import digest
from .protocol import decode, WireError

MAX_DOCS = 32
MAX_BYTES = 8192
MAX_FIELDS = 32
KEY = re.compile(r"[a-z][a-z0-9_]{0,63}")


@dataclass(frozen=True)
class Source:
    family: str
    revision: int
    content_hash: str


@dataclass(frozen=True)
class Fact:
    key: str
    value: int | str
    sources: tuple[Source, ...]


@dataclass(frozen=True)
class Reconciliation:
    status: str
    facts: tuple[Fact, ...]
    reasons: tuple[str, ...]
    input_binding: str


def _valid_key(key):
    return type(key) is str and KEY.fullmatch(key) is not None


def _value(value):
    return (type(value) is int and 0 <= value <= 1_000_000
            or type(value) is str and 0 < len(value) <= 128
            and all(ch.isprintable() for ch in value))


CSV_HEADER = ("family", "revision", "key", "type", "value")


def parse_record(raw):
    """Accept JSON or canonical typed CSV; retain raw bytes outside this parser."""
    text = raw.decode("utf-8")
    if not text.startswith(",".join(CSV_HEADER) + "\n") and not text.startswith(",".join(CSV_HEADER) + "\r\n"):
        return decode(text)
    normalized = text.replace("\r\n", "\n")
    rows = list(csv.reader(StringIO(normalized, newline=""), strict=True))
    if not 2 <= len(rows) <= MAX_FIELDS + 1 or tuple(rows[0]) != CSV_HEADER:
        raise ValueError("invalid CSV inventory")
    canonical = StringIO(newline="")
    csv.writer(canonical, lineterminator="\n").writerows(rows)
    if canonical.getvalue() != normalized:
        raise ValueError("noncanonical CSV inventory")
    family, rev = rows[1][:2]
    if not re.fullmatch(r"[1-9][0-9]{0,3}", rev):
        raise ValueError("invalid CSV revision")
    fields = {}
    for row in rows[1:]:
        if len(row) != 5 or row[:2] != [family, rev]:
            raise ValueError("inconsistent CSV record")
        _, _, field, kind, value = row
        if field in fields:
            raise ValueError("duplicate CSV field")
        if kind == "int" and re.fullmatch(r"0|[1-9][0-9]{0,6}", value):
            fields[field] = int(value)
        elif kind == "text":
            fields[field] = value
        else:
            raise ValueError("invalid CSV field type")
    return {"family": family, "revision": int(rev), "fields": fields}


def reconcile(manifest, required, documents):
    if (type(manifest) is not dict or not 1 <= len(manifest) <= MAX_DOCS
            or any(not _valid_key(k) or type(v) is not int or not 1 <= v <= 1000
                   for k, v in manifest.items())
            or type(required) is not tuple or not 1 <= len(required) <= MAX_FIELDS
            or any(not _valid_key(k) for k in required)
            or len(set(required)) != len(required)):
        raise ValueError("invalid controller manifest")
    if (type(documents) is not tuple or len(documents) > MAX_DOCS
            or any(type(raw) is not bytes or len(raw) > MAX_BYTES for raw in documents)):
        raise ValueError("document inventory exceeds bounds")
    hashes = sorted(sha256(raw).hexdigest() for raw in documents)
    binding = digest({"manifest": manifest, "required": sorted(required), "documents": hashes})
    reasons = set()
    selected = {}
    seen = set()
    for raw in documents:
        try:
            item = parse_record(raw)
            if set(item) != {"family", "revision", "fields"}:
                raise ValueError("schema")
            family, revision, fields = item["family"], item["revision"], item["fields"]
            if (not _valid_key(family) or type(revision) is not int or not 1 <= revision <= 1000
                    or type(fields) is not dict or len(fields) > MAX_FIELDS
                    or any(not _valid_key(k) or not _value(v) for k, v in fields.items())):
                raise ValueError("schema")
        except (WireError, ValueError, UnicodeError, TypeError, csv.Error, IndexError):
            reasons.add("malformed_document")
            continue
        if family not in manifest or revision > manifest[family]:
            reasons.add("unapproved_source_or_revision")
            continue
        identity = (family, revision)
        if identity in seen:
            reasons.add("duplicate_revision")
        seen.add(identity)
        if revision != manifest[family]:
            continue
        selected[family] = (fields, Source(family, revision, sha256(raw).hexdigest()))
    if set(selected) != set(manifest):
        reasons.add("missing_current_revision")
    facts = []
    for key in sorted(required):
        values = [(fields[key], source) for fields, source in selected.values() if key in fields]
        if not values:
            reasons.add("missing_fact:" + key)
        elif any(type(value) is not type(values[0][0]) or value != values[0][0]
                 for value, _ in values):
            reasons.add("conflicting_fact:" + key)
        else:
            facts.append(Fact(key, values[0][0], tuple(sorted(
                (source for _, source in values), key=lambda s: s.family))))
    if reasons:
        return Reconciliation("BLOCKED", (), tuple(sorted(reasons)), binding)
    return Reconciliation("VERIFIED_SYNTHETIC", tuple(facts), (), binding)
