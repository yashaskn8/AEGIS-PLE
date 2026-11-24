# AEGIS-PLE

Adaptive Engineering with Grounded Inference and Self-Verification. Educational research prototype for reliable engineering agents.

## Current milestone

A dependency-free synthetic experiment demonstrates an aggregation defect, an independently checked correction, transfer fixtures, a fail-closed verification gate and a bounded candidate comparison. It is NOT a PLE harness, a benchmark submission, a professional engineering tool or evidence of improved PLE performance.

Run with Python 3.12 (no Docker or model API credentials). Install the pinned WebSocket dependency first; tests use loopback only.

```sh
python -m pip install --require-hashes --only-binary=:all: --no-deps -r requirements.txt
python -m aegis.ci
python -m aegis.experiment
python -m aegis.graph_experiment
python -m aegis.policy_search
```

CI runs the mandatory tests and all three experiment commands. The synthetic loopback server is not an official submission. The policy search generates bounded data-only candidate policies and independently compares their outcomes. The graph experiment compares dependency-aware verification with full recomputation on synthetic fixtures; no external cache or arbitrary candidate code is trusted. The candidate comparison recommends a candidate; it cannot promote or modify code. Production/competition release remains blocked.

See [development policy and research plan](docs/DEVELOPMENT.md). [AGENTS.md](AGENTS.md) is preserved from the organizers' public template. Do not interpret it as permission to access competition resources.
