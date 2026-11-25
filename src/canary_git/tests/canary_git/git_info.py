# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any
from typing import cast

import pytest

import canary
import canary_git

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def git(cwd: Path, *args: str) -> str:
    cmd = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    return subprocess.run([*cmd, *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.pyt").write_text("a\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def tracked(file: Path) -> dict[str, Any]:
    info = canary_git.git_info(file)
    assert info is not None
    return info


class FakeJob:
    def __init__(self, file: Path) -> None:
        self.file = file
        self.measurements: dict = {}

    def add_measurement(self, name, value, *, replace=False) -> None:
        self.measurements[name] = value


def test_tracked_clean(repo):
    info = canary_git.git_info(repo / "sub" / "a.pyt")
    assert info == {
        "commit": git(repo, "rev-parse", "HEAD").strip(),
        "dirty": False,
        "root": git(repo, "rev-parse", "--show-toplevel").strip(),
        "path": "sub/a.pyt",
    }


def test_tracked_modified_is_dirty(repo):
    (repo / "sub" / "a.pyt").write_text("changed\n")
    assert tracked(repo / "sub" / "a.pyt")["dirty"] is True


def test_tracked_staged_is_dirty(repo):
    (repo / "sub" / "a.pyt").write_text("changed\n")
    git(repo, "add", "sub/a.pyt")
    assert tracked(repo / "sub" / "a.pyt")["dirty"] is True


def test_other_dirty_file_does_not_make_job_file_dirty(repo):
    (repo / "b.txt").write_text("b\n")
    git(repo, "add", "b.txt")
    git(repo, "commit", "-q", "-m", "b")
    (repo / "b.txt").write_text("changed\n")
    assert tracked(repo / "sub" / "a.pyt")["dirty"] is False


def test_untracked_file(repo):
    (repo / "sub" / "new.pyt").write_text("new\n")
    assert canary_git.git_info(repo / "sub" / "new.pyt") is None


def test_repo_without_commits(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "a.pyt").write_text("a\n")
    git(tmp_path, "add", "a.pyt")
    assert canary_git.git_info(tmp_path / "a.pyt") is None


def test_not_a_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    (tmp_path / "a.pyt").write_text("a\n")
    assert canary_git.git_info(tmp_path / "a.pyt") is None


def test_git_not_on_path(repo, monkeypatch):
    monkeypatch.setenv("PATH", "")
    assert canary_git.git_info(repo / "sub" / "a.pyt") is None


def test_hook_records_measurement(repo):
    job = FakeJob(repo / "sub" / "a.pyt")
    canary_git.canary_runteststart(cast("canary.Job", job))
    assert job.measurements["git"]["path"] == "sub/a.pyt"


def test_hook_skips_untracked(repo):
    (repo / "sub" / "new.pyt").write_text("new\n")
    job = FakeJob(repo / "sub" / "new.pyt")
    canary_git.canary_runteststart(cast("canary.Job", job))
    assert job.measurements == {}


def test_does_not_write_index(repo):
    # Make the index's cached stat info stale so a refreshing git command would rewrite it.
    file = repo / "sub" / "a.pyt"
    os.utime(file, (file.stat().st_atime, file.stat().st_mtime + 10))
    index = repo / ".git" / "index"
    before = index.read_bytes()
    assert tracked(file)["dirty"] is False
    assert index.read_bytes() == before


def test_works_while_index_is_locked(repo):
    (repo / ".git" / "index.lock").touch()
    assert tracked(repo / "sub" / "a.pyt")["dirty"] is False
