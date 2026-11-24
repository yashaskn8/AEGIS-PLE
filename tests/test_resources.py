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

    def test_adaptive_threshold_and_fallback(self):
        from aegis.quality_evidence import (RESOURCE_FIELDS, resource_break_even,
                                           resource_choice, validate_adaptive_report, digest)
        from statistics import median
        # Controller-owned fabricated timing fixture only; not benchmark evidence.
        def pair(repeats, saving):
            rows = []
            for method, setup, wall, checks in (('full',1,100,88),('learned',21,100-saving,48)):
                rows.append(dict(method=method,cases=24*repeats,correct=24*repeats,
                                 checks=checks*repeats,evidence_sha256='a'*64,setup_ns=setup,
                                 wall_ns=wall,cpu_ns=wall,peak_rss_kib=10,total_wall_ns=setup+wall))
            return rows
        def calibration(savings):
            obs = [pair(30,s) for s in savings]
            return dict(scope='synthetic resource comparison',promotion='BLOCKED',rounds=3,repeats=30,
                        observations=obs,median={m:{k:median(r[k] for rows in obs for r in rows if r['method']==m)
                                                for k in RESOURCE_FIELDS} for m in ('full','learned')})
        report = calibration([10,8,6])
        threshold = resource_break_even(report)
        self.assertEqual(threshold,101)
        self.assertEqual(resource_choice(threshold,100),'full')
        self.assertEqual(resource_choice(threshold,101),'learned')
        self.assertIsNone(resource_break_even(calibration([10,8,0])))
        self.assertEqual(resource_choice(None,180),'full')
        with self.assertRaises(ValueError):
            resource_choice(threshold,181)
        cases = []
        for repeats in (1,180):
            chosen = resource_choice(threshold,repeats)
            rows = sorted(pair(repeats,10),key=lambda r:r['method']!=chosen)
            cases.append(dict(repeats=repeats,chosen=chosen,observations=rows,
                              chosen_minus_alternative_ns=rows[0]['total_wall_ns']-rows[1]['total_wall_ns']))
        outcome = dict(scope='synthetic adaptive resource routing',promotion='BLOCKED',
                       calibration_sha256=digest(report),break_even_repeats=threshold,cases=cases)
        validate_adaptive_report(outcome,report)
        outcome['cases'][0]['chosen'] = 'learned'
        with self.assertRaises(ValueError):
            validate_adaptive_report(outcome,report)
