import unittest
from copy import deepcopy

from aegis.resource_experiment import run
from aegis.quality_evidence import validate_resource_pair, validate_resource_report, MAX_RSS_KIB


class Resources(unittest.TestCase):
    def test_isolated_comparison(self):
        report = run(rounds=1,repeats=2)
        self.assertEqual(report['promotion'],'BLOCKED')
        rows = report['observations'][0]
        self.assertEqual([r['correct'] for r in rows],[48,48])
        self.assertEqual([r['checks'] for r in rows],[176,96])
        self.assertEqual(rows[0]['evidence_sha256'],rows[1]['evidence_sha256'])
        for field,value in (('peak_rss_kib',MAX_RSS_KIB+1),('correct',47),('evidence_sha256','wrong')):
            altered = deepcopy(rows)
            altered[1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_resource_pair(altered,2)

        report["median"]["learned"]["wall_ns"] += 1
        with self.assertRaises(ValueError):
            validate_resource_report(report,rounds=1,repeats=2)

    def test_invalid_budget(self):
        for rounds,repeats in ((0,1),(4,1),(1,31),(True,1)):
            with self.assertRaises(ValueError):
                run(rounds=rounds,repeats=repeats)
