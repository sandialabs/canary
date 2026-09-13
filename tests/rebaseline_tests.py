# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for _canary.subcommands.rebaseline — iter_lockfiles and filter_jobs_by_keywords."""

import json
from pathlib import Path

import pytest

from _canary.subcommands.rebaseline import filter_jobs_by_keywords
from _canary.subcommands.rebaseline import iter_lockfiles


# ---------------------------------------------------------------------------
# iter_lockfiles
# ---------------------------------------------------------------------------


def test_iter_lockfiles_single_file(tmp_path):
    lockfile = tmp_path / "testcase.lock"
    lockfile.write_text("{}")
    result = list(iter_lockfiles(lockfile))
    assert result == [lockfile]


def test_iter_lockfiles_wrong_filename_raises(tmp_path):
    wrong = tmp_path / "wrong_name.lock"
    wrong.write_text("{}")
    with pytest.raises(ValueError, match="testcase.lock"):
        list(iter_lockfiles(wrong))


def test_iter_lockfiles_nonexistent_raises(tmp_path):
    missing = tmp_path / "nonexistent"
    with pytest.raises(ValueError, match="no such file or directory"):
        list(iter_lockfiles(missing))


def test_iter_lockfiles_empty_directory(tmp_path):
    result = list(iter_lockfiles(tmp_path))
    assert result == []


def test_iter_lockfiles_directory_with_one_lockfile(tmp_path):
    subdir = tmp_path / "job1"
    subdir.mkdir()
    lockfile = subdir / "testcase.lock"
    lockfile.write_text("{}")
    result = list(iter_lockfiles(tmp_path))
    assert len(result) == 1
    assert result[0] == lockfile


def test_iter_lockfiles_directory_with_multiple_lockfiles(tmp_path):
    for i in range(3):
        subdir = tmp_path / f"job{i}"
        subdir.mkdir()
        (subdir / "testcase.lock").write_text("{}")
    result = list(iter_lockfiles(tmp_path))
    assert len(result) == 3


def test_iter_lockfiles_nested_directories(tmp_path):
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    lockfile = deep / "testcase.lock"
    lockfile.write_text("{}")
    result = list(iter_lockfiles(tmp_path))
    assert lockfile in result


def test_iter_lockfiles_ignores_non_lockfiles(tmp_path):
    subdir = tmp_path / "job1"
    subdir.mkdir()
    (subdir / "testcase.lock").write_text("{}")
    (subdir / "stdout.txt").write_text("output")
    result = list(iter_lockfiles(tmp_path))
    assert len(result) == 1


# ---------------------------------------------------------------------------
# filter_jobs_by_keywords
# ---------------------------------------------------------------------------


class _FakeSpec:
    def __init__(self, keywords=None):
        self.keywords = keywords or []
        self.implicit_keywords = []


class _FakeJob:
    def __init__(self, keywords=None):
        self.spec = _FakeSpec(keywords)


def test_filter_jobs_by_keywords_none_returns_all():
    jobs = [_FakeJob(["fast"]), _FakeJob(["slow"])]
    result = filter_jobs_by_keywords(jobs, None)
    assert result == jobs


def test_filter_jobs_by_keywords_empty_list_returns_all():
    jobs = [_FakeJob(["fast"]), _FakeJob(["slow"])]
    result = filter_jobs_by_keywords(jobs, [])
    assert result == jobs


def test_filter_jobs_by_keywords_matching():
    fast = _FakeJob(["fast", "unit"])
    slow = _FakeJob(["slow", "integration"])
    result = filter_jobs_by_keywords([fast, slow], ["fast"])
    assert fast in result
    assert slow not in result


def test_filter_jobs_by_keywords_no_match_returns_empty():
    jobs = [_FakeJob(["fast"]), _FakeJob(["slow"])]
    result = filter_jobs_by_keywords(jobs, ["nonexistent"])
    assert result == []


def test_filter_jobs_by_keywords_all_match():
    jobs = [_FakeJob(["fast"]), _FakeJob(["fast", "smoke"])]
    result = filter_jobs_by_keywords(jobs, ["fast"])
    assert len(result) == 2


def test_filter_jobs_by_keywords_negation():
    fast = _FakeJob(["fast"])
    slow = _FakeJob(["slow"])
    result = filter_jobs_by_keywords([fast, slow], ["not slow"])
    # "not slow" should include only jobs without "slow"
    assert fast in result
    assert slow not in result
