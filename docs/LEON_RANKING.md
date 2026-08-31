# Leon's ShopSense Search and Ranking Guide

Run commands below from the repository root. This guide describes the reviewed
candidate and replaceable reference integration, not completed teammate integration.

Build an AI shopping agent that asks useful follow-up questions and recommends the customer's hidden target product within at most 10 turns.

## What You Receive

- A frozen catalog of 50,000 products from the `Clothing_Shoes_and_Jewelry` category of Amazon Reviews 2023.
- 200 labeled public sessions for local development.
- A weak BM25 starter agent and deterministic local evaluator.
- The Agent API contract and scoring rules.

The organizer releases 800 additional sessions after the Devpost deadline for
teams to evaluate using their submitted, frozen Git commit. See the
[official final evaluation FAQ](https://github.com/TechJam2026/techjam-conversational-search/blob/9c9e7c9ff6705142d6ab386dc1c432fc529df893/docs/final_evaluation_faq.md).

## Task

For each session, your agent receives an anonymized preference profile and a short customer message. Raw user IDs, review text, timestamps, and purchase history are never disclosed. On every turn the agent may:

- ask a natural clarification question in `message` and identify one requested field in `ask_attribute`;
- return a ranked list of up to 10 catalog `parent_asin` values;
- do both in the same response.

The session ends when the target product appears in the scored Top 10 or after turn 10. Sessions cover Buying, Browsing, Intent Override, and Boundary behavior.

## Download the Catalog

Download `catalog.jsonl.gz` from the
[official participant-kit release](https://github.com/TechJam2026/techjam-conversational-search/releases/tag/participant-kit), then run:

```bash
gzip -dk catalog.jsonl.gz
mv catalog.jsonl data/catalog.jsonl
```

Verify the downloaded file using the published `SHA256SUMS` file.

Expected participant-kit archive SHA256:

```text
07FD142631FD6B03E2B4D09988C3EB7D53720E9D57010C79DB48EEAADA50A8F8
```

## Run the Starter

Python 3.10 or later is recommended. The starter uses only the Python standard library.

```bash
python3 -m evaluator.local_evaluator
```

Edit `starter/agent.py` to implement your system. Do not edit the evaluator or public labels when reporting your local score.
The command writes per-session results and aggregate metrics to `results.json`.

## ShopSense Search and Ranking

The participant agent now keeps active session evidence and delegates search to a
deterministic, offline ranker:

- `starter/catalog.py` normalizes the frozen catalog and builds an in-memory FTS5 index.
- `starter/profile_adapter.py` converts mapping, dataclass, or object profiles into one
  immutable search-side view and supports field aliases or a custom adapter.
- `starter/retrieval.py` runs weighted lexical, category, exact-clause, and structured routes,
  then combines them with reciprocal-rank fusion.
- `starter/budget.py` shares conservative numeric bounds between retrieval and ranking.
- `starter/ranker.py` applies missing-safe hard, soft, and negative constraints and
  returns at most ten valid unique products in deterministic order.
- `starter/evidence.py` builds optional demo evidence outside the official response.
- `starter/conversation.py` is a replaceable offline reference brain; conversation
  interpretation and question selection remain Shayna-owned.

### Stable Ranker Boundary

After confirming the team's field semantics, Rhea can pass Shayna's profile through
the adapter. `Ranker` accepts dictionaries, dataclasses,
and attribute-based objects. Common aliases such as `current_category`,
`target_category`, `active_query_terms`, `hard_constraints`, `soft_preferences`,
`negative_constraints`, `no_preferences`, and `attributes_asked` are normalized at
one boundary:

```python
from starter.ranker import Ranker

ranker = Ranker("data/catalog.jsonl")
recommendations = ranker.rank(shayna_profile, top_k=10)
question_stats = ranker.attribute_stats(shayna_profile, candidate_limit=100)
demo_evidence = ranker.build_demo_evidence(shayna_profile, recommendations)

# Optional: get recommendations and question context from one search, not two.
recommendations, question_stats = ranker.rank_with_stats(shayna_profile)
```

Teams with a different profile schema can inject an adapter whose `adapt(profile)`
method returns `NormalizedShopperProfile`:

```python
ranker = Ranker("data/catalog.jsonl", profile_adapter=team_adapter)
```

Adapter semantics to agree before integration:

- A named nested active/current state is a **complete intent snapshot**, not a
  partial patch. Omitted intent fields do not inherit potentially stale root
  state. Use a custom adapter if the team's schema instead represents deltas.
- An explicit `active_constraints` collection is authoritative, even when empty.
  Inactive constraints and attributes marked no-preference are excluded. Shayna
  must also remove superseded/no-preference terms from the active query text.
- Constraints may supply attribute/value, hard/soft strength, include/exclude
  polarity, confidence, and source turn. Invalid explicit confidence is not
  upgraded to certainty. Aggregate preferences remain only a weak prior.
- Structured budget operators and min/max bounds are retained. Supported USD or
  unspecified-currency bounds include `<`, `<=`, `>`, `>=`, `=`, and ranges.
  Unsupported currencies/syntax and missing prices remain unknown; no currency
  conversion is inferred. Bare or approximate amounts retain the legacy
  plus/minus max($5, 25%) band; prefer explicit bounds in the team profile.

Candidate statistics use observed value frequencies as an approximate answer
distribution, counting unknown metadata and specifically ambiguous material
values as survivors. Already-asked, no-preference, and exhausted attributes are
omitted. These statistics support Shayna's policy; they do not select a question.
Material negation handling is conservative and local, not general language
understanding. Demo snippets quote actual supporting catalog text or omit the
claim when no short supporting snippet is available.

`rank_detailed()` exposes route sizes and relaxation diagnostics for tests and the
demo. Those diagnostics and `build_demo_evidence()` are sidecars and must never be
placed in `Agent.respond()`.

### Thin Agent Integration

`starter.agent.Agent` accepts an injectable conversation brain, ranking backend, and
official response composer. A future Shayna/Rhea integration therefore replaces the
brain or passes the already-structured profile to `Ranker`; retrieval does not import
or depend on the starter parser. `OfficialResponseComposer` allow-lists only
`message`, `ask_attribute`, and `recommendations`.

The bundled `ReferenceConversationBrain` exists only to keep the released evaluator
runnable. Its broad `other` clarification policy is evaluator-sensitive. The official
FAQ confirms the same deterministic templates and question-response policy for
final evaluation; it does not guarantee the same product/session outcomes. Actual
Shayna/Rhea integration remains unverified until their implementations are supplied.

Run the complete test and evaluation workflow on Windows:

```powershell
python -m unittest discover -s tests -v
python -m evaluator.local_evaluator --catalog data/catalog.jsonl --dataset data/public_set.jsonl --output results.json

# Development audit: retain complete session results AND timing/provenance.
# Choose fresh output names; the audit refuses to overwrite existing artifacts.
python -m experiments.benchmark_runtime --catalog data/catalog.jsonl --dataset data/public_set.jsonl --output results_audit_summary.json --results-output results_audit_sessions.json
```

The implementation requires no model credentials, third-party packages, or network
access at runtime. SQLite FTS5 is used when available; a deterministic weighted-Python
lexical fallback is included for Python builds without FTS5. SQLite access is
serialized so interleaved sessions can safely share the read-only index. Public
evaluation metrics and local timing observations are recorded in
`experiments/scoreboard.md`; they are development evidence, not private-set guarantees.
See [the team handoff](../experiments/TEAM_HANDOFF.md) for the exact adapter agreement,
integration tests, ownership boundaries, and remaining category/budget policy limit.

### Isolated Source Validation

The following creates a **new retained directory outside the checkout**, copies an
explicit allow-list of source/tests/public evaluation inputs, verifies file hashes,
and runs tests plus the official evaluator in a separate Python `-I` process:

```powershell
python -B -m experiments.verify_snapshot --destination ..\shopsense-validation\candidate-01 --evaluate
```

Use a fresh destination each time. Existing directories are never overwritten and
the runner never deletes snapshots. The catalog is copied (about 61 MB), not linked.
Credentials, `.git`, prior results, and unrelated workspace files are not copied.
Python socket/DNS calls are blocked during tests/evaluation, and runtime import
paths are checked to ensure the copied code was used. This is not an OS-wide
network sandbox. Keep `snapshot_manifest.json`, `snapshot_validation.json`,
`results_snapshot_summary.json`, and `results_snapshot_sessions.json` together.

This checks an uncommitted source package independently of the original checkout;
it is not a Git clone or evidence that a reviewed commit has already been submitted.
Rhea still needs to validate the actual submitted commit after team integration.

### Final Evaluation Handoff

The official FAQ at commit `9c9e7c9` supersedes earlier assumptions about the final
environment: network/API use is allowed and there are no standardized organizer
startup, RAM, or per-response limits. This implementation remains offline by choice;
the sub-second p95, 30-second initialization, and 2 GiB goals are team engineering
targets, not official disqualification thresholds.

Before submission, Rhea should freeze the agreed runnable solution commit and record
the setup, catalog checksum, dependencies, hardware, and model configuration. After
the final package is released, do not change the agent, prompts, indexes, or other
solution components. Run the unmodified official evaluator from that submitted
commit and retain the full `results.json` including sessions, submitted SHA, and
execution/environment details. The development audit is supporting evidence, not a
replacement for that required final run. Non-LLM runtime needs no credentials and
incurs no model API cost; any future model integration must disclose dependencies,
real usage, estimated cost, and required environment-variable names, never values.

The included weak BM25 starter scores Hit Rate@10 `0.125`, MRR `0.068034`, and
MTTC `9.81` on the released public set. See `docs/baseline_results.json`.

## Agent Interface

```python
class Agent:
    def reset(self, session_id: str, user_profile: dict) -> None:
        ...

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        return {
            "message": "Do you have a material preference?",
            "ask_attribute": "material",
            "recommendations": [
                {"parent_asin": "B000..."},
                {"parent_asin": "B001..."}
            ],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30}
        }
```

`ask_attribute` is one of `category`, `material`, `color`, `size`, `style`, `brand`, `budget`, `feature`, `use_case`, `other`, or `null`. See `docs/agent_api_contract.json`.

## Technical Metrics

- **Hit Rate@10:** fraction of sessions that find the target within 10 turns.
- **MRR:** mean reciprocal rank of the target; a miss contributes zero.
- **MTTC:** mean first-hit turn; a miss is assigned turn 11.
- **Reported token usage:** prompt and completion tokens returned by the team's model client.

```text
TechnicalScore = 0.50 × HitRate@10 + 0.30 × MRR + 0.20 × Efficiency
Efficiency = clip((11 - MTTC) / 10, 0, 1)
```

`TechnicalScore` is an objective input to the `Technical Execution` assessment. It is not a separate judging criterion and does not represent the entire `Technical Execution` score.

Only exact `parent_asin` equality produces a hit. Core metrics are also reported by scenario.

## Model Choice and Cost

Teams may use any legally accessible LLM API or local model. Teams manage their own credentials and must never commit API keys. Model choice, estimated cost, token usage, and latency must be disclosed. Token usage is a feasibility metric, not part of the core technical score. The organizer does not provide or reimburse model API credits; teams are responsible for any costs incurred through optional external services.

## Files

```text
data/public_set.jsonl             200 labeled development sessions
docs/competition_specification.md participant rules and evaluation protocol
docs/agent_api_contract.json      machine-readable Agent contract
docs/evaluation_config.json       scoring configuration
docs/baseline_results.json        reproducible weak-starter reference score
starter/agent.py                  editable weak starter
evaluator/local_evaluator.py      public-set simulator and scorer
```

## Judging and Submission Policy

- Participant submission requirements: `docs/submission_rules.md`
- Organizer-only final judging controls: `organizer/JUDGING_RUNBOOK.md`
- Organizer private release checklist: `organizer/private_release_checklist.md`
- Judging day operations SOP: `organizer/JUDGING_DAY_SOP.md`

## Data Source

The catalog and sessions are derived from Amazon Reviews 2023 by McAuley Lab, UCSD. See `DATA_ATTRIBUTION.md` before using or redistributing the data.
Sessions are sampled deterministically from the official Clothing 5-core leave-last-out split and joined to the frozen catalog.
