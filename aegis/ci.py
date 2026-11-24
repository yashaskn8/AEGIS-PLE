"""Fail closed on unexpected, missing, skipped or unsuccessful unit tests."""

import sys
import unittest

EXPECTED = {
    "test_defect", "test_correction", "test_schema_and_exception",
    "test_fixture_validation", "test_missing_duplicate_stale_and_failed_evidence",
    "test_transfer_and_bounded_recommendation",
    "test_seeded_differential_and_metamorphic", "test_boundary_cases",
}
EXPECTED_IDS = {"tests.test_foundation.Foundation." + name for name in EXPECTED}


EXPECTED_IDS |= {"tests.test_constraints.Constraints." + name for name in (
    "test_contradictory_evidence", "test_decimal_context", "test_graph_schema",
    "test_dependency_invalidation", "test_missing_and_compound_failures",
    "test_failure_not_cached", "test_candidate_data_not_executable",
    "test_randomized_differential", "test_experiment",
)}


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def main() -> int:
    suite = unittest.defaultTestLoader.discover("tests", top_level_dir=".")
    ids = [test.id() for test in flatten(suite)]
    if len(ids) != len(EXPECTED_IDS) or set(ids) != EXPECTED_IDS:
        print(f"Test inventory mismatch: expected={sorted(EXPECTED_IDS)} actual={sorted(ids)}",
              file=sys.stderr)
        return 1
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if (not result.wasSuccessful() or result.testsRun != len(EXPECTED_IDS)
            or result.skipped or result.expectedFailures or result.unexpectedSuccesses):
        print("Mandatory synthetic test gate FAILED", file=sys.stderr)
        return 1
    print("Mandatory synthetic test gate VERIFIED; competition promotion remains BLOCKED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
