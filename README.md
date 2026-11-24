# AEGIS-PLE

Adaptive Engineering with Grounded Inference and Self-Verification. Educational research prototype for reliable engineering agents.

## Current milestone

A dependency-free synthetic experiment demonstrates an aggregation defect, an independently checked correction, transfer fixtures, a fail-closed verification gate and a bounded candidate comparison. It is NOT a PLE harness, a benchmark submission, a professional engineering tool or evidence of improved PLE performance.

Run with Python 3.12 (no Docker, network, model API or credentials):

```sh
python -m aegis.ci
python -m aegis.experiment
```

CI runs both commands. The candidate comparison recommends a candidate; it cannot promote or modify code. Production/competition release remains blocked.

See [development policy and research plan](docs/DEVELOPMENT.md). [AGENTS.md](AGENTS.md) is preserved from the organizers' public template. Do not interpret it as permission to access competition resources.
