# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import json
import multiprocessing as mp
import os
from pathlib import Path

import pytest

from _canary.util.filesystem import atomic_write
from _canary.util.filesystem import file_lock
from _canary.util.filesystem import force_symlink
from _canary.util.filesystem import remove


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


def test_working_dir_restores_cwd_on_exception(tmp_path):
    from _canary.util.filesystem import working_dir

    start = os.getcwd()
    with pytest.raises(RuntimeError):
        with working_dir(tmp_path / "sub", create=True):
            assert os.getcwd() == str((tmp_path / "sub").resolve())
            raise RuntimeError("boom")
    assert os.getcwd() == start


def test_remove_unlinks_symlink_to_directory(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)

    remove(link)

    assert not link.exists()
    assert target.exists()


def test_force_symlink_replaces_dangling_symlink(tmp_path: Path) -> None:
    target = tmp_path / "real"
    target.write_text("x")
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "missing")

    force_symlink(str(target), str(link))

    assert link.is_symlink()
    assert os.readlink(link) == str(target)


def test_force_symlink_refuses_real_directory(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.write_text("x")
    dest = tmp_path / "dest"
    dest.mkdir()

    with pytest.raises(IsADirectoryError):
        force_symlink(str(src), str(dest))
