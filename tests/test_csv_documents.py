import csv
from hashlib import sha256
from io import StringIO
import json
import unittest

from aegis.deterministic_route import solve
from aegis.document_agent import Scripted, chunks_for, solve as scripted_solve
from aegis.document_experiment import cases, record
from aegis.documents import reconcile
from aegis.models import Profile
from aegis.firewall import digest
from aegis.process_verify import verify_in_process

HEADER = b'family,revision,key,type,value\n'
M = {'register': 2, 'summary': 1}
R = ('inventory_count',)


def csv_doc(family, revision, fields):
    buf = StringIO(newline='')
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(HEADER.decode().strip().split(','))
    for key, value in fields.items():
        w.writerow((family, revision, key, 'int' if type(value) is int else 'text', value))
    return buf.getvalue().encode()


class CSVDocuments(unittest.IsolatedAsyncioTestCase):
    def test_mixed_provenance_and_typed_values(self):
        fields = {'inventory_count': 4, 'label': 'Room "A", 東', 'code': '004'}
        raw = csv_doc('register', 2, fields).replace(b'\n', b'\r\n')
        other = json.dumps({'family': 'summary', 'revision': 1, 'fields': fields}).encode()
        result = solve(M, tuple(fields), (raw, other))
        self.assertEqual(result['status'], 'VERIFIED_SYNTHETIC')
        for fact in result['output']['facts']:
            self.assertEqual(fact['value'], fields[fact['key']])
            self.assertEqual(fact['sources'][0]['content_hash'], sha256(raw).hexdigest())
        self.assertEqual(result, solve(M, tuple(fields), (other, raw)))
        self.assertEqual(result['model_calls'], 0)

    def test_cross_format_conflicts_and_duplicates(self):
        raw = csv_doc('register', 2, {'inventory_count': 4})
        for docs in ((raw, record('summary', 1, 5)),
                     (raw, record('register', 2, 4), record('summary', 1, 4)),
                     (raw, csv_doc('summary', 1, {'inventory_count': '4'}))):
            result = solve(M, R, docs)
            self.assertEqual(result['status'], 'BLOCKED')
            self.assertIsNone(result['output'])
            self.assertFalse(verify_in_process(M, R, docs, {}))

    def test_malformed_csv_rejected(self):
        for line in (b'register\n', b'register,02,inventory_count,int,4\n',
                     b'register,2,inventory_count,int,04\n', b'register,2,inventory_count,int,4',
                     b'register,2,inventory_count,int,"4"\n', b'register,2,inventory_count,text,"x\n',
                     b'register,2,inventory_count,text,x"y\n',
                     b'register,2,inventory_count,int,4\nregister,2,inventory_count,int,4\n',
                     b'register,2,inventory_count,int,4\nsummary,1,other,int,1\n',
                     b'register,2,inventory_count,text,\x00\n'):
            with self.subTest(line=line):
                docs = (HEADER + line, record('summary', 1, 4))
                self.assertEqual(reconcile(M, R, docs).status, 'BLOCKED')
                # Bind a plausible, complete proposal to the malformed bytes;
                # rejection must not be explained by a missing proposal schema.
                hashes = [sha256(d).hexdigest() for d in docs]
                proposal = {"input_binding": digest({"manifest": M, "required": list(R),
                                                       "documents": sorted(hashes)}),
                            "facts": [{"key": R[0], "value": 4,
                                       "sources": [{"family": "register", "revision": 2, "content_hash": hashes[0]},
                                                   {"family": "summary", "revision": 1, "content_hash": hashes[1]}]}]}
                self.assertFalse(verify_in_process(M, R, docs, proposal))

    def test_fixed_category_transfer(self):
        # Alternate source format without changing existing controller labels.
        for case in cases():
            mixed = []
            for i, raw in enumerate(case.documents):
                try:
                    doc = json.loads(raw)
                    if i % 2 == 0 and doc['fields']:
                        raw = csv_doc(doc['family'], doc['revision'], doc['fields'])
                except (ValueError, KeyError):
                    pass
                mixed.append(raw)
            outcome = solve(M, R, tuple(mixed))
            actual = outcome['output']['facts'][0]['value'] if outcome['output'] else None
            self.assertEqual(actual, case.expected, (case.category, case.name))

    async def test_scripted_provider_mixed_input(self):
        docs = (csv_doc('register', 2, {'inventory_count': 4}), record('summary', 1, 4))
        expected = solve(M, R, docs)['output']
        profile = Profile.parse('google-cloud/gemini-4-neon')
        provider = Scripted([chunks_for(profile.model, expected)])
        result = await scripted_solve(M, R, docs, profile, provider)
        self.assertEqual(result.status, 'VERIFIED_SYNTHETIC')
        self.assertEqual(result.output, expected)
        self.assertEqual(result.calls, 1)
