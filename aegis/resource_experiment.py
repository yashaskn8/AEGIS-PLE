"""Measure a fixed fictional verification workload, not frontier-model costs.

Each round runs the two policies in fresh interpreter processes. Equal evidence
is mandatory; speed is an observation, not an acceptance threshold. The limits
are resource ceilings for this tiny experiment, not production capacity claims.
"""
from dataclasses import asdict
import json
import platform
import resource
from statistics import median
import subprocess
import sys
from time import perf_counter_ns, process_time_ns

from .constraints import Controller
from .firewall import digest
from .graph_experiment import NODES, CHECKS
from .learned_policy import fresh, load
from .quality_evidence import (RESOURCE_METHODS as METHODS, RESOURCE_ROUNDS as ROUNDS,
                               RESOURCE_REPEATS as REPEATS, RESOURCE_FIELDS,
                               validate_resource_pair, validate_resource_report)


def worker(method, repeats):
    if method not in METHODS or type(repeats) is not int or not 1 <= repeats <= REPEATS:
        raise ValueError("invalid resource experiment configuration")
    if platform.system() != "Linux":
        raise RuntimeError("RSS units require Linux")
    setup_start = perf_counter_ns()
    workload = fresh()
    policy = load().nodes if method == "learned" else frozenset()
    setup_ns = perf_counter_ns() - setup_start
    start, cpu = perf_counter_ns(), process_time_ns()
    checks = correct = 0
    sequence = []
    for _ in range(repeats):
        controller = Controller(NODES, CHECKS)
        for facts, expected in workload:
            result = controller.evaluate(facts, reuse_nodes=policy)
            correct += result.verified is expected
            checks += result.evaluated
            sequence.append([asdict(item) for item in result.evidence])
    wall_ns, cpu_ns = perf_counter_ns() - start, process_time_ns() - cpu
    return {"method":method,"cases":len(workload)*repeats,"correct":correct,
            "checks":checks,"evidence_sha256":digest(sequence),"setup_ns":setup_ns,
            "wall_ns":wall_ns,"cpu_ns":cpu_ns,"total_wall_ns":setup_ns+wall_ns,
            "peak_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def run(rounds=ROUNDS, repeats=REPEATS):
    if type(rounds) is not int or not 1 <= rounds <= ROUNDS or type(repeats) is not int or not 1 <= repeats <= REPEATS:
        raise ValueError("resource experiment exceeds declared budget")
    observations = []
    for index in range(rounds):
        rows = []
        for method in METHODS if index % 2 == 0 else tuple(reversed(METHODS)):
            result = subprocess.run([sys.executable,"-B","-m","aegis.resource_experiment",
                                     method,str(repeats)],capture_output=True,timeout=12,check=True)
            if len(result.stdout) > 4096 or result.stderr:
                raise ValueError("unexpected resource worker output")
            rows.append(json.loads(result.stdout))
        validate_resource_pair(rows,repeats)
        observations.append(rows)
    summary = {method:{key:median(r[key] for rows in observations for r in rows if r["method"] == method)
                       for key in RESOURCE_FIELDS}
               for method in METHODS}
    report = {"scope":"synthetic resource comparison","rounds":rounds,"repeats":repeats,
              "observations":observations,"median":summary,"promotion":"BLOCKED"}
    validate_resource_report(report,rounds=rounds,repeats=repeats)
    return report


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print(json.dumps(run(),sort_keys=True))
    elif len(sys.argv) == 3:
        print(json.dumps(worker(sys.argv[1],int(sys.argv[2])),sort_keys=True))
    else:
        raise SystemExit("invalid resource experiment arguments")
