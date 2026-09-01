"""Public-development failure traces. Never imported by runtime modules.

Targets are read only here, for diagnostics; the Agent receives only the official
message/profile interface. This tool does not modify the evaluator or labels.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl
from starter.agent import Agent
from starter.ranker import constraint_relation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-results", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--per-scenario", type=int, default=2)
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--dataset", default="data/public_set.jsonl")
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(output)
    previous = json.loads(Path(args.prior_results).read_text(encoding="utf-8"))
    selected = set()
    counts = {}
    for row in previous["sessions"]:
        scenario = row["scenario_type"]
        if not row["hit"] and counts.get(scenario, 0) < args.per_scenario:
            selected.add(row["sample_id"])
            counts[scenario] = counts.get(scenario, 0) + 1
    samples = [s for s in load_jsonl(args.dataset) if s["sample_id"] in selected]
    ids, categories, products = catalog_index(args.catalog)
    agent = Agent(args.catalog, conversation_mode="shayna")
    traces = []

    class Tracer:
        def reset(self, session_id, user_profile):
            self.sample = samples[len(traces)]
            self.row = {"sample_id": self.sample["sample_id"],
                        "scenario": self.sample["scenario_type"], "turns": []}
            traces.append(self.row)
            agent.reset(session_id, user_profile)

        def respond(self, session_id, user_message, turn, top_k):
            response = agent.respond(session_id, user_message, turn, top_k)
            canonical = agent.ranker._adapt(agent.brain.sessions[session_id])
            ranked = agent.ranker._ranked_candidates(canonical)
            target_id = self.sample["ground_truth"]["parent_asin"]
            target = agent.ranker.catalog.products[target_id]
            self.row["turns"].append({
                "turn": turn, "message": user_message,
                "ask_attribute": response["ask_attribute"],
                "canonical": asdict(canonical),
                "target_pool_rank": ranked.index(target_id) + 1 if target_id in ranked else None,
                "target_relations": [constraint_relation(target, c) for c in canonical.constraints],
            })
            return response

    try:
        result = evaluate(Tracer(), samples, ids, categories, products)
        with output.open("x", encoding="utf-8") as handle:
            json.dump({"result": result, "traces": traces}, handle, indent=2,
                      default=lambda value: sorted(value) if isinstance(value, (set, frozenset)) else str(value))
        print(json.dumps({"samples": len(samples), "output": str(output), "metrics": {
            k: v for k, v in result.items() if k != "sessions"}}, indent=2))
    finally:
        agent.close()


if __name__ == "__main__":
    main()
