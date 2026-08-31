from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path


DEFAULT_SEED = "shopsense-leon-public-v1"
STRATIFY_FIELDS = ("scenario_type", "difficulty_bucket", "category_bucket")


def stable_split(samples: list[dict], validation_size: int, seed: str = DEFAULT_SEED) -> dict:
    """Return a fixed stratified split containing IDs, never ground truth."""

    if not 0 <= validation_size <= len(samples):
        raise ValueError("validation_size must be between zero and the sample count")
    groups: dict[tuple[str, ...], list[dict]] = defaultdict(list)
    for sample in samples:
        key = tuple(str(sample.get(field, "unknown")) for field in STRATIFY_FIELDS)
        groups[key].append(sample)

    target_fraction = validation_size / len(samples) if samples else 0.0
    quotas = {key: math.floor(len(rows) * target_fraction) for key, rows in groups.items()}
    remaining = validation_size - sum(quotas.values())
    remainder_order = sorted(
        groups,
        key=lambda key: (
            -(len(groups[key]) * target_fraction - quotas[key]),
            key,
        ),
    )
    for key in remainder_order[:remaining]:
        quotas[key] += 1

    dev_ids: list[str] = []
    validation_ids: list[str] = []
    strata: list[dict] = []
    for key in sorted(groups):
        rows = sorted(
            groups[key],
            key=lambda sample: hashlib.sha256(
                f"{seed}\0{sample['sample_id']}".encode("utf-8")
            ).hexdigest(),
        )
        quota = quotas[key]
        selected = {str(sample["sample_id"]) for sample in rows[:quota]}
        validation_ids.extend(selected)
        dev_ids.extend(str(sample["sample_id"]) for sample in rows if str(sample["sample_id"]) not in selected)
        strata.append(
            {
                **dict(zip(STRATIFY_FIELDS, key)),
                "total": len(rows),
                "dev": len(rows) - quota,
                "validation": quota,
            }
        )

    return {
        "seed": seed,
        "stratify_fields": list(STRATIFY_FIELDS),
        "dev_ids": sorted(dev_ids),
        "validation_ids": sorted(validation_ids),
        "strata": strata,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the fixed public dev/validation manifest")
    parser.add_argument("--dataset", default="data/public_set.jsonl")
    parser.add_argument("--output", default="experiments/public_split.json")
    parser.add_argument("--validation-size", type=int, default=40)
    parser.add_argument("--seed", default=DEFAULT_SEED)
    args = parser.parse_args()

    with Path(args.dataset).open(encoding="utf-8") as handle:
        samples = [json.loads(line) for line in handle if line.strip()]
    manifest = stable_split(samples, args.validation_size, args.seed)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "dev": len(manifest["dev_ids"]),
                "validation": len(manifest["validation_ids"]),
                "output": str(output),
            }
        )
    )


if __name__ == "__main__":
    main()
