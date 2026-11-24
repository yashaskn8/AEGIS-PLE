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


EXPECTED_IDS |= {"tests.test_protocol.ProtocolTests." + name for name in (
    "test_round_trip", "test_invalid_opening", "test_mismatched_id", "test_cancel",
    "test_timeout", "test_incomplete_files", "test_bad_paths_and_writes",
    "test_concurrent_request_rejected", "test_strict_json",
)}
EXPECTED_IDS |= {"tests.test_protocol.Models." + name for name in (
    "test_all_declarations", "test_provider_controls",
)}


EXPECTED_IDS |= {"tests.test_runtime.Runtime." + name for name in (
    "test_socket_report", "test_socket_corrupt_readback",
    "test_socket_changed_source", "test_socket_cancel",
)}
EXPECTED_IDS |= {"tests.test_runtime.Policies." + name for name in (
    "test_generated_inventory", "test_equal_evidence_and_transfer",
    "test_invalid_policy", "test_source_validation",
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
