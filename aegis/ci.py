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


EXPECTED_IDS |= {"tests.test_governance.Governance." + name for name in (
    "test_historical_replay", "test_stale_and_missing_ci", "test_missing_skipped_duplicate_steps",
    "test_false_metrics_and_selection", "test_budget_exhaustion", "test_budget_reuse_and_change",
    "test_invalid_budget",
)}


EXPECTED_IDS |= {"tests.test_repair.Repair." + name for name in (
    "test_verified_first_attempt", "test_targeted_retry", "test_budget_no_acceptance",
    "test_stale_and_malformed", "test_wrong_model_and_usage", "test_timeout_and_zero_budget",
    "test_reject_actions", "test_invalid_profile", "test_latest_historical_record",
)}


EXPECTED_IDS |= {"tests.test_extensions.Extensions." + name for name in (
    "test_usage", "test_no_completion_before_start", "test_catalog_handshake",
    "test_catalog_not_declared", "test_catalog_compound_failures",
)}
EXPECTED_IDS |= {"tests.test_extensions.Streams." + name for name in (
    "test_stream_collection", "test_missing_and_invalid_usage", "test_reject_tool_and_wrong_model",
)}


EXPECTED_IDS |= {"tests.test_documents.Documents." + name for name in (
    "test_fixed_category_experiment", "test_order_invariance", "test_no_obsolete_fallback",
    "test_conflicting_provenance", "test_unapproved_and_duplicate",
    "test_malformed_boolean_duplicate_keys", "test_manifest_and_limits",
    "test_required_fact_absent",
)}


EXPECTED_IDS |= {"tests.test_learning.Learning." + name for name in (
    "test_reproduce_archived_policy", "test_fresh_retention",
    "test_reject_consistent_but_fabricated_archive", "test_document_archive_replay",
    "test_oversize_archive",
)}


EXPECTED_IDS |= {"tests.test_document_agent.DocumentAgent." + name for name in (
    "test_integrated_repair_experiment", "test_source_conflict_no_provider",
    "test_forged_provenance_and_boolean", "test_reported_input_over_budget",
    "test_no_retry_after_unaccounted_stream", "test_zero_and_timeout",
    "test_transport_error_no_unaccounted_retry", "test_late_reply_after_cancellation",
)}
EXPECTED_IDS |= {"tests.test_document_agent.GateNegative." + name for name in (
    "test_missing_test_inventory_fails", "test_failed_and_skipped_results_fail",
)}


EXPECTED_IDS |= {"tests.test_process.Process." + name for name in (
    "test_distinct_worker_agrees_on_valid_and_invalid", "test_reject_changed_source_and_proposal",
    "test_worker_timeout_and_malformed_response", "test_published_frontier", "test_invalid_matrix",
)}


EXPECTED_IDS |= {"tests.test_deterministic.Deterministic." + name for name in (
    "test_zero_call_route","test_worker_veto","test_discipline_matrix","test_matrix_inconsistent",
)}


EXPECTED_IDS |= {"tests.test_document_runtime.DocumentRuntime." + name for name in (
    "test_success","test_conflict_blocks_write","test_prewrite_source_change",
    "test_postwrite_source_change","test_corrupt_readback","test_cancel_during_write",
)}


EXPECTED_IDS |= {"tests.test_quality.Quality." + name for name in (
    "test_mutation_anchor_exact","test_mutation_syntax",
    "test_no_unrelated_mutant_kill","test_narrow_secret_patterns",
)}


EXPECTED_IDS |= {"tests.test_distribution.Distribution." + name for name in (
    "test_reproducible_order","test_mismatched_source_and_commit",
    "test_unsafe_paths","test_extra_member_rejected",
)}


EXPECTED_IDS.add("tests.test_decimal_precision.DecimalPrecision.test_all_zero_and_large_boundary")


EXPECTED_IDS |= {"tests.test_quality_evidence.QualityEvidence." + name for name in (
    "test_exact_historical_record", "test_modified_record_rejected",
    "test_structural_rejection_even_with_new_digest", "test_download_exact_and_tampered",
    "test_download_extra_inner_member", "test_preflight_record_and_required_report",
)}


EXPECTED_IDS |= {"tests.test_workflow_policy.WorkflowPolicy." + name for name in (
    "test_exact_current_workflow", "test_original_yaml_parse_failure",
    "test_valid_yaml_with_changed_gate_rejected", "test_duplicate_keys_and_aliases_rejected",
    "test_scalar_type_changes_rejected",
)}


EXPECTED_IDS |= {"tests.test_document_scale.DocumentScale." + name for name in (
    "test_maximum_supported_inventory", "test_seeded_multifield_transfer_and_compound_faults",
    "test_oversized_request_rejected_before_launch_and_by_worker",
)}


EXPECTED_IDS.add("tests.test_protocol.Models.test_aggregate_content_budget_and_unicode")
EXPECTED_IDS.add("tests.test_extensions.Streams.test_stream_byte_boundary_and_invalid_unicode")


EXPECTED_IDS |= {"tests.test_deadline.Deadline." + name for name in (
    "test_late_receive_poisoned", "test_late_send_poisoned",
    "test_expired_success_refused_but_error_allowed",
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
