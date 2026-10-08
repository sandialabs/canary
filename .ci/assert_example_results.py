#!/usr/bin/env python3

"""Validate that the bundled Canary examples produced their intended outcomes.

This is stricter than checking the aggregate session return code alone.  The
return code is a bitmask that can match for unrelated reasons; this verifier
asserts that specific example jobs landed in the outcomes the examples are meant
to demonstrate.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

INDEX_FILE = Path("examples") / "index.json"


def run_canary_query(*args: str) -> object:
    cp = subprocess.run(["canary", *args], check=True, capture_output=True, text=True)
    return json.loads(cp.stdout)


def load_expected_results() -> dict[str, str]:
    data = json.loads(INDEX_FILE.read_text())
    expected_results = data.get("expected_results")
    if not isinstance(expected_results, dict):
        raise ValueError(f"{INDEX_FILE}: expected_results must be an object")
    outcomes: dict[str, str] = {}
    for fullname, spec in expected_results.items():
        if not isinstance(spec, dict):
            raise ValueError(f"{INDEX_FILE}: {fullname!r} must map to an object")
        outcome = spec.get("outcome")
        if not isinstance(outcome, str) or not outcome:
            raise ValueError(f"{INDEX_FILE}: {fullname!r} must define a non-empty outcome")
        outcomes[fullname] = outcome
    return outcomes


def main() -> int:
    expected_job_outcomes = load_expected_results()

    jobs = run_canary_query("query", "jobs", "--session", "latest", "--terse")
    assert isinstance(jobs, list)
    by_name = Counter(job["fullname"] for job in jobs)
    for name, count in by_name.items():
        if count != 1:
            print(
                f"Expected exactly one latest-session job named {name!r}, found {count}",
                file=sys.stderr,
            )
            return 1

    actual_job_outcomes = {job["fullname"]: job["status"]["outcome"] for job in jobs}
    mismatches = {
        name: {"expected": expected, "actual": actual_job_outcomes.get(name)}
        for name, expected in expected_job_outcomes.items()
        if actual_job_outcomes.get(name) != expected
    }
    if mismatches:
        print("Unexpected example job outcomes", file=sys.stderr)
        print(json.dumps(mismatches, indent=2, sort_keys=True), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
