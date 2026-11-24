"""Deterministic-first route for fully specified fictional inventories.

No provider is necessary when trusted structured facts determine every field.
Unresolved sources block instead of asking a model to invent missing facts.
"""
import json
from .documents import reconcile
from .document_agent import verified_projection
from .document_experiment import cases
from .process_verify import verify_in_process


def solve(manifest, required, documents):
    source = reconcile(manifest, required, documents)
    if source.status != "VERIFIED_SYNTHETIC":
        return {"status":"BLOCKED","output":None,"reasons":list(source.reasons),"model_calls":0}
    proposal = verified_projection(source)
    if not verify_in_process(manifest, required, documents, proposal):
        return {"status":"BLOCKED","output":None,"reasons":["independent_process_rejected"],"model_calls":0}
    return {"status":"VERIFIED_SYNTHETIC","output":proposal,"reasons":[],"model_calls":0}


def experiment():
    rows = []
    for case in cases():
        result = solve({"register":2,"summary":1},("inventory_count",),case.documents)
        actual = result["output"]["facts"][0]["value"] if result["output"] is not None else None
        rows.append({"category":case.category,"case":case.name,"correct":actual == case.expected,
                     "false_accept":case.expected is None and result["output"] is not None,
                     "model_calls":result["model_calls"]})
    if not all(r["correct"] and not r["false_accept"] for r in rows):
        raise RuntimeError("deterministic route mandatory failure")
    return {"scope":"deterministic synthetic document route","cases":len(rows),
            "correct":sum(r["correct"] for r in rows),"false_accepts":sum(r["false_accept"] for r in rows),
            "model_calls":sum(r["model_calls"] for r in rows),"promotion":"BLOCKED"}


if __name__ == "__main__":
    print(json.dumps(experiment(),sort_keys=True))
