# ShopSense

TikTok TechJam 2026 Shopping Copilot project for the Conversational E-Commerce Search Challenge.

Build an AI shopping agent that asks useful follow-up questions and recommends the customer's hidden target product within at most 10 turns.

## Team Ownership

- Shayna: Product DNA, conversation state, constraints, useful questions.
- Leon: catalog search, filtering, ranking, Top 10 recommendations.
- Rhea: integration, official agent contract, evaluator, README, final submission.

## Current Release Candidate

The integrated release candidate combines Shayna's profile/question modules with
Leon ranking through Rhea's official `starter.agent.Agent` entry point.

Verified public-set result:

```text
Hit Rate@10: 0.98
MRR: 0.690403
MTTC: 2.96
TechnicalScore: 0.857921
```

Run the release checks:

```bash
python3 -m unittest
python3 -m evaluator.local_evaluator
```

Optional local demo UI:

```bash
python3 demo/server.py
```

Then open `http://127.0.0.1:8000`.

See [final results](docs/FINAL_RESULTS.md) and
[Rhea's submission checklist](docs/SUBMISSION_CHECKLIST.md). For Devpost,
use [the written submission draft](docs/DEVPOST_SUBMISSION_DRAFT.md) and
[the demo video script](docs/DEMO_VIDEO_SCRIPT.md).

## Leon's Search and Ranking Candidate

For combining both teammates' branches, start with
[Rhea's morning handoff](docs/RHEA_MORNING_HANDOFF.md). It identifies the real
interfaces, measured integration status, catalogue setup, and final verification commands.

The feature-branch implementation and integration guide are documented in
[Leon ranking guide](docs/LEON_RANKING.md), with measured results in
[the scoreboard](experiments/scoreboard.md) and interface decisions in
[the handoff](experiments/TEAM_HANDOFF.md).

With both feature branches combined, `starter/agent.py` automatically uses Shayna's
actual parser/question policy through [the tested bridge](docs/COMBINED_AGENT.md).
It runs Leon's search and candidate statistics once before selecting the question.
`starter/conversation.py` remains an explicitly selectable reference comparison;
its historical score must not be attributed to the Shayna integration. These changes
retain Shayna's profile/question ownership and Rhea's integration/release ownership.
Existing baseline figures below
describe the original starter, not this candidate. Rhea reviews and merges the PR;
feature branches must not push directly to `main`.

## What You Receive

- A frozen catalog of 50,000 products from the `Clothing_Shoes_and_Jewelry` category of Amazon Reviews 2023.
- 200 labeled public sessions for local development.
- A weak BM25 starter agent and deterministic local evaluator.
- The Agent API contract and scoring rules.

The organizer keeps 800 additional sessions private for final evaluation.

## Task

For each session, your agent receives an anonymized preference profile and a short customer message. Raw user IDs, review text, timestamps, and purchase history are never disclosed. On every turn the agent may:

- ask a natural clarification question in `message` and identify one requested field in `ask_attribute`;
- return a ranked list of up to 10 catalog `parent_asin` values;
- do both in the same response.

The session ends when the target product appears in the scored Top 10 or after turn 10. Sessions cover Buying, Browsing, Intent Override, and Boundary behavior.

## Download the Catalog

Download the official participant catalog release and verify both checksums.
Windows PowerShell setup:

```powershell
New-Item -ItemType Directory -Force .\data | Out-Null

curl.exe -L `
  -o .\data\catalog.jsonl.gz `
  "https://github.com/TechJam2026/techjam-conversational-search/releases/download/participant-kit/catalog.jsonl.gz"

if ((Get-FileHash .\data\catalog.jsonl.gz -Algorithm SHA256).Hash -ne "07FD142631FD6B03E2B4D09988C3EB7D53720E9D57010C79DB48EEAADA50A8F8") {
    throw "Compressed catalog checksum mismatch"
}

python -c "import gzip,shutil; src=gzip.open(r'data/catalog.jsonl.gz','rb'); dst=open(r'data/catalog.jsonl','wb'); shutil.copyfileobj(src,dst); src.close(); dst.close()"

if ((Get-FileHash .\data\catalog.jsonl -Algorithm SHA256).Hash -ne "DA979B05A68AF864CB0DCF9EE6A81C010C7E66A57978AD286C7A2E005FC69A67") {
    throw "Decompressed catalog checksum mismatch"
}

python -B -m unittest discover -s tests -v
python -B -m evaluator.local_evaluator
python -B demo/server.py
```

Catalog URL:

```text
https://github.com/TechJam2026/techjam-conversational-search/releases/download/participant-kit/catalog.jsonl.gz
```

Compressed SHA256: `07FD142631FD6B03E2B4D09988C3EB7D53720E9D57010C79DB48EEAADA50A8F8`

Decompressed SHA256: `DA979B05A68AF864CB0DCF9EE6A81C010C7E66A57978AD286C7A2E005FC69A67`

## Run the Agent

Python 3.10 or later is recommended. The starter uses only the Python standard library.

```powershell
python -B -m evaluator.local_evaluator
```

The implemented `starter/agent.py` selects Shayna when both reviewed branches are
combined. Do not edit the evaluator or public labels when reporting your score.
The command writes per-session results and aggregate metrics to `results.json`;
use the identity-checked benchmark in [the combined guide](docs/COMBINED_AGENT.md)
to verify which conversation implementation was actually evaluated.

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

Only exact `parent_asin` equality produces a hit. Core metrics are also reported by scenario.

## Model Choice and Cost

Teams may use any legally accessible LLM API or local model. Teams manage their own credentials and costs and must never commit API keys. Model choice, estimated cost, token usage, and latency must be disclosed. Token usage is a feasibility metric, not part of the core technical score. The organizer does not provide or reimburse model API keys, tokens or credits; see the [official final-evaluation FAQ](https://github.com/TechJam2026/techjam-conversational-search/blob/9c9e7c9ff6705142d6ab386dc1c432fc529df893/docs/final_evaluation_faq.md). This implementation uses no model API.

## Files

```text
data/public_set.jsonl             200 labeled development sessions
docs/competition_specification.md participant rules and evaluation protocol
docs/agent_api_contract.json      machine-readable Agent contract
docs/evaluation_config.json       scoring configuration
docs/baseline_results.json        reproducible weak-starter reference score
starter/agent.py                  implemented combined Agent entrypoint
evaluator/local_evaluator.py      public-set simulator and scorer
```

## Judging and Submission Policy

- Participant submission requirements: `docs/submission_rules.md`
- Rhea submission checklist: `docs/SUBMISSION_CHECKLIST.md`
- Final public-set result: `docs/FINAL_RESULTS.md`

## Data Source

The catalog and sessions are derived from Amazon Reviews 2023 by McAuley Lab, UCSD. See `DATA_ATTRIBUTION.md` before using or redistributing the data.
Sessions are sampled deterministically from the official Clothing 5-core leave-last-out split and joined to the frozen catalog.
