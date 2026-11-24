import unittest
from aegis.quality import Mutation, apply_mutation, classify, secret_findings


class Quality(unittest.TestCase):
    def test_mutation_anchor_exact(self):
        m = Mutation("sample","sample.py","x = 1","x = 2","test")
        self.assertEqual(apply_mutation("x = 1\n",m),"x = 2\n")
        for source in ("x = 0\n","x = 1\nx = 1\n"):
            with self.assertRaises(ValueError):
                apply_mutation(source,m)

    def test_mutation_syntax(self):
        with self.assertRaises(SyntaxError):
            apply_mutation("x = 1",Mutation("sample","a.py","x = 1","x = (","test"))

    def test_no_unrelated_mutant_kill(self):
        baseline = {"run":1,"failures":[],"errors":[],"skipped":0,
                    "expected_failures":0,"unexpected_successes":0}
        self.assertTrue(classify(baseline,"t",mutant=False))
        self.assertFalse(classify(baseline,"t",mutant=True))
        self.assertTrue(classify(dict(baseline,failures=["t"]),"t",mutant=True))
        for change in ({"errors":["t"]},{"failures":["other"]},{"run":0},{"skipped":1}):
            self.assertFalse(classify(dict(baseline,**change),"t",mutant=True))

    def test_narrow_secret_patterns(self):
        self.assertEqual(secret_findings("sample.py",b"MODEL_API_KEY"),[])
        self.assertEqual(secret_findings(".env",b""),["credential_file"])
        self.assertIn("github_token",secret_findings("a.txt",b"ghp_"+b"A"*36))
        self.assertIn("private_key",secret_findings("a.txt",b"-----BEGIN "+b"PRIVATE KEY-----"))
