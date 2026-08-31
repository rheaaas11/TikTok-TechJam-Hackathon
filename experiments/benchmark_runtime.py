from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import statistics
import subprocess
import sys
import time
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import AbstractSet

from evaluator.local_evaluator import ALLOWED_ATTRIBUTES, catalog_index, evaluate, load_jsonl
from starter.agent import Agent


class TimedAgent:
    def __init__(self, agent: Agent, valid_ids: AbstractSet[str] | None = None) -> None:
        self.agent = agent
        self.valid_ids = valid_ids
        self.latencies: list[float] = []
        self.exception_count = 0
        self.reset_exception_count = 0
        self.audited_responses = 0
        self.invalid_responses = 0
        self.audit_violations: Counter[str] = Counter()
        self.recommendation_lengths: Counter[int] = Counter()

    def reset(self, session_id: str, user_profile: dict) -> None:
        try:
            self.agent.reset(session_id, user_profile)
        except Exception:
            self.reset_exception_count += 1
            raise

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        started = time.perf_counter()
        try:
            response = self.agent.respond(session_id, user_message, turn, top_k)
        except Exception:
            self.exception_count += 1
            raise
        finally:
            self.latencies.append(time.perf_counter() - started)
        self._audit(response, top_k)
        return response

    def _audit(self, response: object, top_k: int) -> None:
        """Inspect raw output without fixing it or changing official scoring.

        Violation counters count affected responses, not individual bad items.
        No messages, profiles, credentials, or exception text are retained.
        """

        self.audited_responses += 1
        errors: set[str] = set()
        if not isinstance(response, dict):
            errors.add("response_not_dict")
        else:
            required = {"message", "ask_attribute", "recommendations"}
            if not required <= response.keys():
                errors.add("required_fields_missing")
            if response.keys() - (required | {"usage"}):
                errors.add("extra_response_fields")
            if not isinstance(response.get("message"), str):
                errors.add("invalid_message")
            attribute = response.get("ask_attribute")
            if attribute is not None and (
                not isinstance(attribute, str) or attribute not in ALLOWED_ATTRIBUTES
            ):
                errors.add("invalid_ask_attribute")
            recommendations = response.get("recommendations")
            if not isinstance(recommendations, list):
                errors.add("recommendations_not_list")
            else:
                self.recommendation_lengths[len(recommendations)] += 1
                limit = min(10, max(0, top_k))
                if len(recommendations) > limit:
                    errors.add("team_recommendation_limit_exceeded")
                seen: set[str] = set()
                for item in recommendations:
                    if not isinstance(item, dict):
                        errors.add("recommendation_not_dict")
                        continue
                    if item.keys() - {"parent_asin", "score"}:
                        errors.add("extra_recommendation_fields")
                    parent_asin = item.get("parent_asin")
                    if not isinstance(parent_asin, str) or not parent_asin.strip():
                        errors.add("invalid_parent_asin")
                    else:
                        if parent_asin in seen:
                            errors.add("duplicate_parent_asin")
                        seen.add(parent_asin)
                        if self.valid_ids is not None and parent_asin not in self.valid_ids:
                            errors.add("unknown_parent_asin")
                    if "score" in item:
                        score = item["score"]
                        if (isinstance(score, bool) or not isinstance(score, (int, float))
                                or (isinstance(score, float) and not math.isfinite(score))):
                            errors.add("invalid_recommendation_score")
            if "usage" in response:
                usage = response["usage"]
                fields = {"prompt_tokens", "completion_tokens"}
                if not isinstance(usage, dict) or usage.keys() != fields:
                    errors.add("invalid_usage")
                elif any(type(usage[field]) is not int or usage[field] < 0 for field in fields):
                    errors.add("invalid_usage")
        if errors:
            self.invalid_responses += 1
            self.audit_violations.update(errors)

    def audit_summary(self) -> dict:
        return {
            "responses_audited": self.audited_responses,
            "invalid_responses": self.invalid_responses,
            "violations_by_affected_response": dict(sorted(self.audit_violations.items())),
            "recommendation_count_distribution": {
                str(length): count for length, count in sorted(self.recommendation_lengths.items())
            },
            "catalog_membership_checked": self.valid_ids is not None,
            "team_gate": "at most min(top_k, 10); stricter than official raw maxItems=100",
        }


def percentile(values: list[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(probability * len(ordered)) - 1)
    return ordered[index]


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_provenance(catalog: str | Path, dataset: str | Path, root: Path | None = None) -> dict:
    root = root or Path(__file__).resolve().parents[1]
    source_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted((root / "starter").glob("*.py"))
    }
    digest = hashlib.sha256()
    for name, value in source_hashes.items():
        digest.update(f"{name}\0{value}\n".encode("utf-8"))

    def git_value(arguments: list[str]) -> str | None:
        try:
            result = subprocess.run(["git", *arguments], cwd=root, capture_output=True,
                                    text=True, timeout=10, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    head = git_value(["rev-parse", "HEAD"])
    status = git_value(["status", "--porcelain"])
    return {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "git_head": head,
        "git_dirty": None if status is None else bool(status),
        "starter_source_sha256": digest.hexdigest(),
        "starter_file_sha256": source_hashes,
        "data": {
            name: {"path": str(Path(path).resolve()), "sha256": file_sha256(path)}
            for name, path in (("catalog", catalog), ("dataset", dataset))
        },
    }


def process_peak_working_set() -> dict:
    """Windows process-lifetime peak, including evaluator/catalog setup, not agent-only memory."""

    scope = "process lifetime peak; includes evaluator/catalog setup, not incremental Agent memory"
    if sys.platform != "win32":
        return {"available": False, "scope": scope, "reason": "Windows API unavailable on this platform"}
    try:
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in (
                    "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                    "PagefileUsage", "PeakPagefileUsage",
                )
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters),
                                              wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise OSError("GetProcessMemoryInfo failed")
        return {"available": True, "peak_working_set_bytes": int(counters.PeakWorkingSetSize),
                "scope": scope, "method": "Windows GetProcessMemoryInfo.PeakWorkingSetSize"}
    except (AttributeError, OSError, TypeError) as error:
        return {"available": False, "scope": scope, "reason": type(error).__name__}


def output_paths(output: str | Path, results_output: str | Path | None = None) -> tuple[Path, Path | None]:
    summary = Path(output).resolve()
    results = Path(results_output).resolve() if results_output is not None else None
    if results == summary:
        raise ValueError("--output and --results-output must resolve to different paths")
    for path in (summary, results):
        if path is not None and path.exists():
            raise FileExistsError(f"Refusing to overwrite existing output: {path}")
    return summary, results


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Time every turn of the public evaluator")
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--dataset", default="data/public_set.jsonl")
    parser.add_argument("--output", default="results_runtime_benchmark.json")
    parser.add_argument("--results-output", help="Fresh path for complete official results including sessions")
    args = parser.parse_args(argv)
    try:
        summary_path, results_path = output_paths(args.output, args.results_output)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    # Reserve fresh paths before expensive work. Exclusive creation also protects
    # against a file appearing between the preflight check and opening the path.
    with ExitStack() as stack:
        summary_handle = stack.enter_context(summary_path.open("x", encoding="utf-8"))
        results_handle = (stack.enter_context(results_path.open("x", encoding="utf-8"))
                          if results_path is not None else None)
        provenance = collect_provenance(args.catalog, args.dataset)
        samples = load_jsonl(args.dataset)
        catalog_ids, categories, products = catalog_index(args.catalog)
        started = time.perf_counter()
        agent = Agent(args.catalog)
        initialization = time.perf_counter() - started
        try:
            timed = TimedAgent(agent, valid_ids=catalog_ids)
            evaluation_started = time.perf_counter()
            result = evaluate(timed, samples, catalog_ids, categories, products)
            wall = time.perf_counter() - evaluation_started
            summary = {
                "initialization_seconds": round(initialization, 6),
                "evaluation_wall_seconds": round(wall, 6),
                "timed_turns": len(timed.latencies),
                "agent_exceptions": timed.exception_count,
                "reset_exceptions": timed.reset_exception_count,
                "turn_latency_ms": {
                    "p50": round(statistics.median(timed.latencies) * 1000, 6) if timed.latencies else 0.0,
                    "p95": round(percentile(timed.latencies, 0.95) * 1000, 6),
                    "maximum": round(max(timed.latencies, default=0.0) * 1000, 6),
                },
                "raw_response_audit": timed.audit_summary(),
                "memory": process_peak_working_set(),
                "provenance": provenance,
                "official_results_path": str(results_path) if results_path is not None else None,
                "metrics": {key: value for key, value in result.items() if key != "sessions"},
            }
            if results_handle is not None:
                results_handle.write(json.dumps(result, indent=2) + "\n")
                results_handle.flush()
            summary_handle.write(json.dumps(summary, indent=2) + "\n")
            summary_handle.flush()
            print(json.dumps(summary, indent=2))
        finally:
            agent.close()


if __name__ == "__main__":
    main()
