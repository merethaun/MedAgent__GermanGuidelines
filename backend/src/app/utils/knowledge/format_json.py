#!/usr/bin/env python3
import json
import sys
from collections import OrderedDict


def transform(records):
    """
    Group records by `question` and map each group to:
    {
      question, expected_answer, expected_retrievals, gen_res:[{...}]
    }
    """
    grouped = OrderedDict()
    
    for i, r in enumerate(records):
        print(f"Processing record {i + 1} of {len(records)}", end="\r", flush=True)
        q = r.get("question")
        if q is None:  # skip malformed item without a question
            continue
        
        if q not in grouped:
            grouped[q] = {
                "question": q,
                "expected_answer": r.get("expected_answer"),
                "expected_retrievals": r.get("expected_retrievals", []),
                "gen_res": [],
            }
        else:
            # If the first item didn’t have these, fill from later ones
            if not grouped[q].get("expected_answer") and r.get("expected_answer"):
                grouped[q]["expected_answer"] = r["expected_answer"]
            if not grouped[q].get("expected_retrievals") and r.get("expected_retrievals"):
                grouped[q]["expected_retrievals"] = r["expected_retrievals"]
        
        grouped[q]["gen_res"].append(
            {
                "gen_res_id": r.get("gen_res_id"),
                "gen_run_name": r.get("gen_run_name"),
                "actual_response": r.get("actual_response"),
                "actual_retrievals": r.get("actual_retrievals", []),
                "correctness_score": r.get("correctness_score"),
                "reason": r.get("reason"),
                "retrieval_recall": r.get("retrieval_recall"),
                "retrieval_precision": r.get("retrieval_precision"),
            },
        )
    
    return list(grouped.values())


if __name__ == "__main__":
    # Usage:
    #   python script.py input.json   -> reads from file
    #   cat input.json | python script.py  -> reads from stdin
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)
    
    result = transform(data)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
