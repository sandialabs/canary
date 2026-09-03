# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import json
import multiprocessing as mp
from pathlib import Path

from _canary.util.filesystem import atomic_write
from _canary.util.filesystem import file_lock


def test_file_lock_creates_sidecar(tmp_path: Path) -> None:
    target = tmp_path / "data.json"
    with file_lock(target):
        atomic_write(target, json.dumps({"count": 1}))
    assert target.exists()
    assert target.with_name(target.name + ".lock").exists()
    assert json.loads(target.read_text())["count"] == 1


def _increment_worker(target_str: str, iterations: int) -> None:
    target = Path(target_str)
    for _ in range(iterations):
        with file_lock(target):
            data = json.loads(target.read_text()) if target.exists() else {"count": 0}
            data["count"] += 1
            atomic_write(target, json.dumps(data))


def test_file_lock_serializes_concurrent_read_modify_write(tmp_path: Path) -> None:
    target = tmp_path / "counter.json"
    nprocs = 6
    iterations = 40

    ctx = mp.get_context("fork")
    procs = [
        ctx.Process(target=_increment_worker, args=(str(target), iterations)) for _ in range(nprocs)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
        assert p.exitcode == 0

    # Without locking, concurrent read-modify-write would lose updates.
    assert json.loads(target.read_text())["count"] == nprocs * iterations
