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

## Experiment 0002 — dependency-aware verification

Predeclared hypothesis: a task-local dependency graph can reduce deterministic check executions without changing any verification evidence versus full recomputation. Budget: seven synthetic scenarios, one incremental and one full run each, plus 100 seeded perturbations. Acceptance: identical observations in every scenario, fewer actual check invocations, rejected missing inputs, cycles, contradictory evidence and compound failures, and preserved original tests. Stop on any mismatch. The metric is check calls, not wall time, token cost or PLE accuracy. Check functions must be pure, deterministic, trusted and fixed during the controller lifetime; no candidate code is loaded by this controller. Dependencies and relevant fact keys must be complete. No external cache, hidden task data, or promotion.

Review: official protocol blob 8ec13aeddb270ce581a5920224b6c856feb50a23 and rules blob 8bc47a001c24be0ed3157a9c30ce191f6d72a3a6. Current web guide: https://ple-bench.com/competition/guide. Conflicting artifact rules remain unresolved. Branch main reported protected=false, rulesets empty, protection details inaccessible (403). No independent gate or arbitrary code sandbox is claimed. This change is limited to trusted checks and synthetic JSON candidate data. The existing in-process candidate experiment remains trusted-only.

Research rationale: https://arxiv.org/abs/2507.19457 (GEPA, instance-level feedback and Pareto candidate selection) and https://arxiv.org/abs/2506.13131 (AlphaEvolve, evaluator-driven search). Neither establishes performance on PLE or validates this graph. No unrestricted self-modification is enabled.

## Milestone 0003 — synthetic protocol and model profiles

Sources: upstream protocol blob 8ec13aeddb270ce581a5920224b6c856feb50a23, model documentation blob 735569d27e8fd01741d189470a2c93e4647afaa9. Hypothesis: strict frame correlation, deadline accounting, and terminal guards prevent ambiguous completion during synthetic file transport. Acceptance: original tests retained; valid read/write round trip and rejection of mismatched IDs, malformed JSON, unsupported frames, incomplete reads, concurrent requests, and cancellation/timeout. Provider profile tests cover eleven documented identifiers and supported effort controls. Budget: synthetic peers only, zero external calls. No official compatibility, socket server, MCP support, provider tool history, live reasoning or model access is claimed. A persistent task ledger is maintained in research/checkpoint.json; CI results are recorded only after observation.

## Milestone 0004 — loopback verification and policy generation

Predeclared acceptance: original 28 tests plus four actual local WebSocket interactions (success, corrupt output, changed input, cancellation) and four candidate-policy/source tests. A report is accepted only after independent arithmetic validation, exact readback and source re-read. The scope is fictional measurements. The server listens only on loopback, not the official evaluator bind address. No model endpoint, shell, MCP, or hidden data is accessed. The WebSocket dependency is hash-pinned from https://pypi.org/project/websockets/15.0.1/#files.

Policy-search hypothesis: generating cache-eligible subsets and comparing each with full recomputation can identify a cheaper verification policy without changing any evidence. Budget: 16 policies x seven development cases, then exactly 32 fresh seeded synthetic transfer steps for the chosen policy; each comparison includes a full-recomputation oracle. Selection uses development only, ties favor smaller policies then lexical order. Every evidence mismatch fails the experiment. Promotion remains blocked regardless of the results. No candidate-generated Python, learning from benchmark data, or protected governance is claimed.

## Milestone 0005 — historical evidence replay and verification budgets

Hypothesis: exact commit/run/step inventory checks reject incomplete or internally inconsistent historical CI records, while a bounded check budget never accepts an unevaluated requirement. Acceptance: all prior tests plus seven regression tests, including stale commits, missing/skipped/duplicate/failed steps, inconsistent metrics, zero budget and changed inputs. Historical evidence was collected from GitHub's run/job API and CI log for commit e1f8c17921be07268a30874624bc9d50132f20c7, run 45434137959, job 138587206278. The record contains only synthetic observations. It is not a signature, an immutable external authority, or current-commit certification. The previous experiment's selected policy matched 7/7 development and 32/32 transfer observations, reducing check calls from 26 to 16 and 100 to 53 respectively. Only 2/32 transfer scenarios were actually feasible; evidence agreement is not task success. No token savings or real benchmark gains are claimed.

The capability inventory records the four published category leaders and explicit research hypotheses; the full matrix and causal transfer experiments remain unfinished. Release and official evaluation remain blocked.

## Milestone 0006 — bounded proposal and repair controller

Predeclared acceptance: previous 43 tests plus nine tests of independently checked structured replies, targeted retries, stale sources, malformed schema, provider identity and reported usage mismatches, timeouts, zero budget, action rejection and historical replay. The controller reserves output allowance before each attempted call and never refunds ambiguous usage. Its scripted providers are synthetic test doubles; no API is invoked and no actual provider latency, cost, or model improvement is measured. The Decimal oracle uses fictional inventory measurements, not engineering safety decisions. Candidate replies cannot invoke code or tools. This is an offline controller, not streaming or native provider support, not a full official agent, and not a sandbox for arbitrary code. The earlier CI evidence was collected from GitHub for commit e78bae31b266a8769f04ab04d67f6956ee2cb9bf, run 45434441700. Promotion remains blocked.

## Milestone 0007 — synthetic protocol extensions
Official protocol and model docs were re-read at blobs 8ec13aeddb270ce581a5920224b6c856feb50a23 and 735569d27e8fd01741d189470a2c93e4647afaa9. Acceptance: retain 52 tests and add eight tests for bounded usage messages, premature terminal frames, declared read-only synthetic catalog initialization/listing, compound response faults, and streamed text/usage correlation. No actual MCP service, model call, shell or external URL is executed. Catalog support is intentionally single-page and synthetic; tool invocation, native model metadata and official validation remain unimplemented. The previous checkpoint commit df87d8be251112a4e4b1a12a3bd7e8d80b0d70b8 passed CI 45434870519.