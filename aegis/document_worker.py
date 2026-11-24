"""Independent trusted verifier for fictional JSON inventory records.

Run as a fixed script with JSON stdin. No dynamic imports, candidate code,
network requests or shell commands. This is process separation, not a sandbox
for hostile Python code or independently protected policy administration.
"""
import base64
from hashlib import sha256
import json
import re
import sys

# Independently bounded for the maximum supported document/provenance inventory.
MAX = 640 * 1024


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def parse(raw):
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("constant")))


def parse_document(raw):
    # Independent narrow CSV parser: metadata cannot contain commas or quotes;
    # only the final value column can use minimal doubled-quote encoding.
    header = "family,revision,key,type,value\n"
    text = raw.decode("utf-8").replace("\r\n", "\n")
    if not text.startswith(header):
        return parse(raw)
    if not text.endswith("\n"):
        raise ValueError("CSV terminator")
    lines = text[len(header):-1].split("\n")
    if not 1 <= len(lines) <= 32:
        raise ValueError("CSV row count")
    identity = None
    fields = {}
    for line in lines:
        family, revision, field, kind, encoded = line.split(",", 4)
        if not key(family) or not key(field) or not re.fullmatch(r"[1-9][0-9]{0,3}", revision):
            raise ValueError("CSV metadata")
        if identity is None:
            identity = (family, revision)
        if identity != (family, revision) or field in fields:
            raise ValueError("CSV identity")
        if encoded.startswith('"'):
            if not re.fullmatch(r'"(?:[^"\r\n]|"")*"', encoded):
                raise ValueError("CSV quote")
            value = encoded[1:-1].replace('""', '"')
            if not any(c in value for c in ',"'):
                raise ValueError("unnecessary CSV quote")
        else:
            if any(c in encoded for c in ',"\r'):
                raise ValueError("CSV unquoted value")
            value = encoded
        if kind == "int" and re.fullmatch(r"0|[1-9][0-9]{0,6}", value):
            fields[field] = int(value)
        elif kind == "text":
            fields[field] = value
        else:
            raise ValueError("CSV type")
    return {"family": identity[0], "revision": int(identity[1]), "fields": fields}


def key(value):
    return type(value) is str and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value) is not None


def verify(request):
    if set(request) != {"manifest", "required", "documents", "proposal"}:
        return False
    manifest, required = request["manifest"], request["required"]
    if (type(manifest) is not dict or not 1 <= len(manifest) <= 32
            or any(not key(k) or type(v) is not int or not 1 <= v <= 1000
                   for k,v in manifest.items())
            or type(required) is not list or not 1 <= len(required) <= 32
            or not all(key(k) for k in required) or len(set(required)) != len(required)):
        return False
    docs = request["documents"]
    if type(docs) is not list or len(docs) > 32:
        return False
    records = {}
    hashes = []
    for encoded in docs:
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > 8192:
            return False
        fingerprint = sha256(raw).hexdigest()
        hashes.append(fingerprint)
        item = parse_document(raw)
        if type(item) is not dict or set(item) != {"family", "revision", "fields"}:
            return False
        family, rev, fields = item["family"], item["revision"], item["fields"]
        if (not key(family) or family not in manifest or type(rev) is not int
                or not 1 <= rev <= manifest[family] or type(fields) is not dict
                or len(fields) > 32 or (family, rev) in records):
            return False
        for k,v in fields.items():
            if not key(k) or not (type(v) is int and 0 <= v <= 1000000
                    or type(v) is str and 0 < len(v) <= 128 and all(c.isprintable() for c in v)):
                return False
        records[family, rev] = (fingerprint, fields)
    if any((family, rev) not in records for family, rev in manifest.items()):
        return False
    facts = []
    for field in sorted(required):
        sources = []
        values = []
        for family, rev in sorted(manifest.items()):
            fingerprint, fields = records[family, rev]
            if field in fields:
                values.append(canonical(fields[field]))
                sources.append({"family": family, "revision": rev, "content_hash": fingerprint})
        if not values or len(set(values)) != 1:
            return False
        facts.append({"key": field, "value": json.loads(values[0]), "sources": sources})
    binding = sha256(canonical({"manifest": manifest, "required": sorted(required),
                               "documents": sorted(hashes)}).encode()).hexdigest()
    expected = {"input_binding": binding, "facts": facts}
    return canonical(request["proposal"]) == canonical(expected)


def main():
    raw = sys.stdin.buffer.read(MAX + 1)
    result = False
    if len(raw) <= MAX:
        try:
            result = verify(parse(raw)) is True
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, AttributeError):
            result = False
    print(canonical({"accepted": result, "request_sha256": sha256(raw).hexdigest()}))


if __name__ == "__main__":
    main()
