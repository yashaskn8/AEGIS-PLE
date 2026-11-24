# Development and acceptance policy

## Scope and blockers

Educational synthetic fixtures only until participation eligibility and applicable permissions are verified. No dataset, model credentials, paid infrastructure, hidden task information, or official artifacts are needed for this milestone. No real-world engineering use.

Official references:
- https://www.kaggle.com/competitions/physical-engineerings-last-exam/rules
- https://github.com/google-research/ple/blob/main/docs/rules.md
- https://ple-bench.com/competition/agents
- https://ple-bench.com/competition/guide
- https://ple-bench.com/leaderboard

Review on 2026-11-24: the Kaggle legal rules page was not readable through the available browser. The public guide lists eight models while the user-supplied announcement lists eleven. The repository rules require matching artifact-generation and declared models; the supplied announcement describes an exception. Organizer confirmation is required. Official AGENTS.md and Apache-2.0 LICENSE copied unchanged from physical-engineerings-last-exam/submission-template (AGENTS blob 25352486aa25e3f5398a58a2e26f08c572ab1087; license blob 261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64). The upstream baseline is not yet imported or run.

## Experiment 0001 (predeclared design)

Hypothesis: rounding after aggregation prevents cumulative rounding errors for bounded nonnegative synthetic integer measurements. Falsifier: a mismatch with the independent Decimal oracle, a regression on a baseline-passing fixture, or failure on a transfer fixture. Budget: exactly two candidates, six fixtures each, no retries or model calls; deterministic tests use 100 seeded generated inputs. Stop after this comparison. Acceptance: all challenger checks verified, strict development improvement, no per-case regression and all transfer cases pass. Candidate output is verified by a controller, not self-reported. Transfer fixtures are published and are not statistically independent secret holdouts; no generalization claim beyond them. A recommendation is not promotion.

## Governance

Keep experiments bounded, preserve negative results, compare under equivalent conditions, never weaken gates to manufacture success. Record exact commits, commands, checks, actual results and uncertainty. No automated code rewriting or production promotion. A candidate and its verifier currently share a trust domain. Independent policy ownership, required remote CI checks, release protection, sandboxed untrusted candidate execution, persistent archives, provider integration, constraint dependencies, protocol checks, real benchmarks and statistical thresholds remain BLOCKED or UNTESTED. Repository CI is not independently immutable until external governance is configured. Do not use this prototype as a competition harness.

## Roadmap

1. Verify synthetic CI and diagnose any failure.
2. Independently protect acceptance policies and establish authorized compute.
3. Audit pinned upstream harness and implement protocol adapter tests with synthetic peers.
4. Add evidence provenance, dependency invalidation, bounded repair and checkpoint integrity.
5. Only when authorized, run official compatibility checks and genuine benchmark experiments. Keep all claims scoped to actual evidence.
