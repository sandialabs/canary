# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Tests for canary_hpc.estimate: conservative per-job runtime estimates."""

from typing import Any

import pytest

import _canary.config as config
from canary_hpc import estimate
from canary_hpc.argparsing import CanaryHPCResourceSetter
from canary_hpc.argparsing import cold_runtime_fraction_type


class FakeJob:
    def __init__(
        self,
        *,
        timeout: float = 300.0,
        multiplier: float = 1.0,
        history: dict[str, Any] | None = None,
        broken_cache: bool = False,
        cache: dict[str, Any] | None = None,
    ) -> None:
        self.id = "f" * 64
        self.timeout = timeout
        self.multiplier = multiplier
        self.history = history
        self.broken_cache = broken_cache
        self.cache = cache

    def total_timeout(self) -> float:
        return self.multiplier * self.timeout

    def load_cached_runs(self) -> dict[str, Any] | None:
        if self.broken_cache:
            raise OSError("unreadable cache")
        if self.cache is not None:
            return self.cache
        if self.history is None:
            return None
        return {"metrics": {"time": self.history}}


def history(mean: float, maximum: float | None = None) -> dict[str, float]:
    return {"mean": mean, "max": mean if maximum is None else maximum, "count": 2}


def test_cold_job_uses_default_fraction_of_timeout():
    job = FakeJob(timeout=300.0)
    assert estimate.DEFAULT_COLD_RUNTIME_FRACTION == 0.75
    assert estimate.estimate_runtime(job) == 225.0


def test_cold_fraction_is_set_from_command_line():
    with config.override():
        config.options.hpc_batch_cold_runtime_fraction = 0.5
        assert estimate.estimate_runtime(FakeJob(timeout=300.0)) == 150.0


def test_cold_estimate_is_capped_at_hard_limit():
    """A fraction above the timeout multiplier cannot exceed the point the job is killed."""
    with config.override():
        config.options.hpc_batch_cold_runtime_fraction = 3.0
        job = FakeJob(timeout=300.0, multiplier=2.0)
        assert estimate.estimate_runtime(job) == job.total_timeout() == 600.0


def test_history_applies_penalty():
    job = FakeJob(timeout=300.0, history=history(60.0))
    assert estimate.estimate_runtime(job) == estimate.RUNTIME_HISTORY_PENALTY * 60.0 == 75.0


def test_history_prefers_recorded_max_over_mean():
    """A few anomalously fast samples drag the mean down; the recorded max does not move."""
    job = FakeJob(timeout=300.0, history=history(40.0, maximum=80.0))
    assert estimate.estimate_runtime(job) == 1.25 * 80.0


def test_history_is_floored_at_fraction_of_timeout():
    job = FakeJob(timeout=300.0, history=history(0.01))
    assert estimate.estimate_runtime(job) == estimate.RUNTIME_FLOOR_FRACTION * 300.0 == 30.0


def test_history_is_capped_at_hard_limit():
    """A stale history longer than the hard limit is capped at that limit."""
    job = FakeJob(timeout=300.0, history=history(900.0))
    assert estimate.estimate_runtime(job) == 300.0
    job = FakeJob(timeout=300.0, multiplier=4.0, history=history(900.0))
    assert estimate.estimate_runtime(job) == 1.25 * 900.0


@pytest.mark.parametrize(
    "cache",
    [
        {"metrics": {}},
        {"metrics": {"time": {"count": 1}}},
        {"metrics": {"time": {"mean": "n/a"}}},
        {"history": {"pass": 1}},
    ],
)
def test_malformed_history_falls_back_to_cold_estimate(cache):
    job = FakeJob(timeout=300.0, cache=cache)
    assert estimate.estimate_runtime(job) == 225.0


def test_unreadable_cache_falls_back_to_cold_estimate():
    assert estimate.estimate_runtime(FakeJob(timeout=300.0, broken_cache=True)) == 225.0


def test_mean_only_history_is_used():
    """Caches written without a ``max`` entry still provide a usable estimate."""
    job = FakeJob(timeout=300.0, history={"mean": 100.0, "count": 1})
    assert estimate.estimate_runtime(job) == 125.0


# ---------------------------------------------------------------------------
# Command-line parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("arg,expected", [("0.75", 0.75), ("1", 1.0), ("2.5", 2.5)])
def test_cold_runtime_fraction_type_accepts_positive_numbers(arg, expected):
    assert cold_runtime_fraction_type(arg) == expected


@pytest.mark.parametrize("arg", ["0", "-0.5", "abc", ""])
def test_cold_runtime_fraction_type_rejects_bad_values(arg):
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        cold_runtime_fraction_type(arg)


@pytest.mark.parametrize(
    "value", ["cold_runtime_fraction=0.4", "cold-runtime-fraction=0.4", "cold_runtime_fraction:0.4"]
)
def test_b_alias_sets_cold_runtime_fraction(value):
    import argparse

    action = CanaryHPCResourceSetter(option_strings=["-b"], dest="hpc_b")
    namespace = argparse.Namespace()
    action(None, namespace, value)
    assert namespace.hpc_batch_cold_runtime_fraction == 0.4
