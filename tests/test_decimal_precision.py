import unittest
from decimal import localcontext
from aegis.aggregation import Fixture, aggregate_first
from aegis.firewall import assess, State


class DecimalPrecision(unittest.TestCase):
    def test_all_zero_and_large_boundary(self):
        with localcontext() as context:
            context.prec = 1
            for values, expected in (((0,)*100, "0"), ((999999,)*100, "100000")):
                result = assess(aggregate_first, Fixture("boundary",values))
                self.assertIs(result.state,State.VERIFIED)
                self.assertEqual(result.evidence[1].expected,expected)
