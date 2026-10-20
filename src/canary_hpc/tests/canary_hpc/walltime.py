# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""User-pinned scheduler wall limits (``--time``/``-t``/``--time-limit``)."""

from pathlib import Path

import pytest

from canary_hpc.batchexec import _parse_wall_seconds
from canary_hpc.walltime import WallTimeError
from canary_hpc.walltime import parse_wall_time
from canary_hpc.walltime import pinned_wall_seconds


@pytest.mark.parametrize(
    "args,expected",
    [
        # Slurm formats; a bare number is minutes
        (["--time=30"], 1800.0),
        (["--time=30:00"], 1800.0),  # MM:SS -- previously parsed as 2e-6 s
        (["--time=90:00"], 5400.0),
        (["--time=1:00:00"], 3600.0),
        (["--time=36:00:00"], 129600.0),
        (["--time=1-00:00:00"], 86400.0),  # previously raised "Invalid duration"
        (["--time=2-12"], 2 * 86400.0 + 12 * 3600.0),
        (["--time=1-02:30"], 86400.0 + 2 * 3600.0 + 30 * 60.0),
        (["-t", "30"], 1800.0),  # -t was previously ignored
        (["-t30:00"], 1800.0),
        (["--time", "45"], 2700.0),
        # unit-suffixed / compound durations
        (["--time=5m"], 300.0),
        (["--time=1h30m"], 5400.0),
        # Flux --time-limit: bare number is seconds (FSD)
        (["--time-limit=3600"], 3600.0),
        (["--time-limit=90m"], 5400.0),
        (["--time-limit=1.5h"], 5400.0),
        # Combined / quoted / last wins
        (["--partition=short --time=10"], 600.0),
        (["--time=5m", "--time=30m"], 1800.0),
        (["--account=X"], None),
        ([], None),
    ],
)
def test_pinned_wall_seconds(args, expected):
    assert pinned_wall_seconds(args) == expected
    assert _parse_wall_seconds(args) == expected


@pytest.mark.parametrize(
    "value", ["0", "00:00", "abc", "1:75:00", "1-25:00:00", "UNLIMITED", "-5", "5parsecs"]
)
def test_invalid_wall_times_rejected(value):
    with pytest.raises(WallTimeError):
        parse_wall_time(value)
    with pytest.raises(WallTimeError):
        pinned_wall_seconds([f"--time={value}"])
    # The diagnostic helper never raises
    assert _parse_wall_seconds([f"--time={value}"]) is None


def test_batch_wall_limit_uses_slurm_semantics(tmp_path: Path):
    from .batchspec import FakeJob
    from .batchspec import make_batch

    batch = make_batch(tmp_path, [FakeJob(id="j1")])
    assert batch.wall_limit(submit_args=["--time=30:00"]) == 1800.0
    assert batch.wall_limit(submit_args=["--time=1-00:00:00"]) == 86400.0
    assert batch.wall_limit(submit_args=["-t", "30"]) == 1800.0
    with pytest.raises(WallTimeError):
        batch.wall_limit(submit_args=["--time=bogus"])
