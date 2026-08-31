"""Copy an explicit source package and validate it without the working checkout.

The destination must be new and outside the source tree. It is retained, never
deleted automatically. This verifies an uncommitted source snapshot, not a Git
clone or submitted commit. Only standard-library dependencies are required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import unittest
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
# -I intentionally excludes cwd and user site packages; import only this copy.
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

PACKAGES = ("starter", "evaluator", "experiments", "tests")
EXTRA_FILES = (
    "README.md", "LICENSE", "DATA_ATTRIBUTION.md", "SHA256SUMS",
    "data/README.md", "data/public_set.jsonl", "docs/agent_api_contract.json",
    "docs/evaluation_config.json", "docs/baseline_results.json",
    "experiments/public_split.json", "experiments/scoreboard.md",
    "experiments/TEAM_HANDOFF.md",
)
REQUIRED = (
    "starter/agent.py", "evaluator/local_evaluator.py",
    "experiments/benchmark_runtime.py", "experiments/verify_snapshot.py",
    "docs/evaluation_config.json", "docs/agent_api_contract.json", "data/public_set.jsonl",
)
NETWORK_CALLS = (
    "socket.create_connection", "socket.socket.connect", "socket.socket.connect_ex",
    "socket.socket.sendto", "socket.getaddrinfo", "socket.gethostbyname",
    "socket.gethostbyname_ex",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_files(source: Path) -> list[Path]:
    source = source.resolve()
    files = {source / name for name in EXTRA_FILES if (source / name).is_file()}
    for package in PACKAGES:
        files.update(path for path in (source / package).rglob("*.py")
                     if not any(part.startswith(".") or part == "__pycache__"
                                for part in path.relative_to(source).parts))
    for name in REQUIRED:
        if source / name not in files:
            raise ValueError(f"Required source file missing: {name}")
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ValueError(f"Source symlink/path escape is unsupported: {path.name}")
    return sorted(files)


def copy_snapshot(source: Path, destination: Path, catalog: Path) -> dict:
    source, destination, catalog = source.resolve(), destination.resolve(), catalog.resolve()
    if destination == source or destination.is_relative_to(source):
        raise ValueError("Destination must be outside the source tree")
    if destination.exists():
        raise FileExistsError("Destination already exists; choose a fresh snapshot directory")
    files = source_files(source)
    if not catalog.is_file():
        raise FileNotFoundError("Catalog file is missing")
    expected = {path.relative_to(source).as_posix(): sha256(path) for path in files}
    expected["data/catalog.jsonl"] = sha256(catalog)
    destination.mkdir(parents=True, exist_ok=False)
    for path in files:
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    shutil.copyfile(catalog, destination / "data/catalog.jsonl")
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_root": str(source),
        "scope": "explicit source snapshot; not a Git clone or submitted commit",
        "file_sha256": expected,
    }
    with (destination / "snapshot_manifest.json").open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    verify_manifest(destination)
    return manifest


def verify_manifest(root: Path) -> dict:
    root = root.resolve()
    manifest = json.loads((root / "snapshot_manifest.json").read_text(encoding="utf-8"))
    for relative, expected in manifest["file_sha256"].items():
        path = root / relative
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            raise ValueError("Manifest path escapes the snapshot")
        if sha256(path) != expected:
            raise ValueError(f"Snapshot changed or copy is incomplete: {relative}")
    return manifest


@contextmanager
def offline_guard():
    """Block Python socket/DNS calls; this is not an OS-wide network sandbox."""
    attempts: list[bool] = []

    def blocked(*args, **kwargs):
        attempts.append(True)
        raise RuntimeError("Network disabled during isolated validation")

    with ExitStack() as stack:
        for name in NETWORK_CALLS:
            stack.enter_context(patch(name, side_effect=blocked))
        yield attempts


def verify_evaluation(root: Path) -> dict:
    """Reject incomplete evidence and errors hidden by evaluator normalization."""
    summary = json.loads((root / "results_snapshot_summary.json").read_text(encoding="utf-8"))
    result = json.loads((root / "results_snapshot_sessions.json").read_text(encoding="utf-8"))
    with (root / "data/public_set.jsonl").open(encoding="utf-8") as handle:
        expected_ids = [json.loads(line)["sample_id"] for line in handle if line.strip()]
    sessions = result.get("sessions")
    if not expected_ids or len(set(expected_ids)) != len(expected_ids) or not isinstance(sessions, list):
        raise ValueError("Dataset or retained session records are invalid")
    actual_ids = [row.get("sample_id") for row in sessions]
    if (len(actual_ids) != len(expected_ids) or set(actual_ids) != set(expected_ids)
            or len(set(actual_ids)) != len(actual_ids) or result.get("sample_count") != len(expected_ids)):
        raise ValueError("Retained session IDs/count do not match the copied dataset")
    if summary.get("metrics") != {key: value for key, value in result.items() if key != "sessions"}:
        raise ValueError("Summary metrics disagree with complete session results")
    audit = summary.get("raw_response_audit", {})
    turns = summary.get("timed_turns", 0)
    if (summary.get("agent_exceptions") != 0 or summary.get("reset_exceptions") != 0
            or audit.get("invalid_responses") != 0 or audit.get("violations_by_affected_response") != {}
            or audit.get("catalog_membership_checked") is not True
            or not isinstance(turns, int) or turns < len(expected_ids)
            or audit.get("responses_audited") != turns
            or sum(audit.get("recommendation_count_distribution", {}).values()) != turns):
        raise ValueError("Agent errors, invalid outputs, or incomplete raw-response auditing detected")
    return {"session_count": len(sessions), "responses_audited": turns,
            "summary_matches_complete_results": True, "raw_response_checks_passed": True}


def validate_inside(root: Path, *, evaluate: bool) -> int:
    if not sys.flags.isolated:
        raise RuntimeError("Run the copied validator with Python -I")
    verify_manifest(root)
    print("Isolated snapshot: verifying tests with socket/DNS calls blocked", flush=True)
    with offline_guard() as attempts:
        suite = unittest.defaultTestLoader.discover(str(root / "tests"), top_level_dir=str(root))
        result = unittest.TextTestRunner(verbosity=1).run(suite)
    report = {
        "python_isolated": bool(sys.flags.isolated), "tests_run": result.testsRun,
        "test_failures": len(result.failures), "test_errors": len(result.errors),
        "test_skips": len(result.skipped), "test_network_calls_blocked": len(attempts),
        "evaluation_requested": evaluate,
    }
    if not result.wasSuccessful():
        with (root / "snapshot_validation.json").open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
        return 1
    if evaluate:
        from experiments.benchmark_runtime import main as benchmark
        print("Tests passed; running the unchanged official evaluator", flush=True)
        with offline_guard() as attempts:
            benchmark(["--catalog", str(root / "data/catalog.jsonl"),
                       "--dataset", str(root / "data/public_set.jsonl"),
                       "--output", str(root / "results_snapshot_summary.json"),
                       "--results-output", str(root / "results_snapshot_sessions.json")])
        report["evaluation_network_calls_blocked"] = len(attempts)
        report["evaluation_integrity"] = verify_evaluation(root)
    verify_manifest(root)
    runtime_origins = {name: str(Path(module.__file__).resolve())
                       for name, module in sys.modules.items()
                       if name.startswith(("starter.", "evaluator.")) and getattr(module, "__file__", None)}
    if any(not Path(path).is_relative_to(root) for path in runtime_origins.values()):
        raise RuntimeError("Runtime imported from outside the isolated snapshot")
    report["runtime_module_origins"] = runtime_origins
    report["manifest_unchanged_after_validation"] = True
    with (root / "snapshot_validation.json").open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if not report.get("evaluation_network_calls_blocked", 0) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--catalog", type=Path, default=ROOT / "data/catalog.jsonl")
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.inside:
        return validate_inside(ROOT, evaluate=args.evaluate)
    if args.destination is None:
        parser.error("--destination must name a new directory outside the source tree")
    copy_snapshot(ROOT, args.destination, args.catalog)
    command = [sys.executable, "-I", "-B", str(args.destination.resolve() / "experiments/verify_snapshot.py"), "--inside"]
    if args.evaluate:
        command.append("--evaluate")
    print(f"Retained source snapshot: {args.destination.resolve()}", flush=True)
    return subprocess.run(command, cwd=args.destination.resolve(), check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
