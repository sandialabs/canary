# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for canary_gitlab.reporter — pure functions and MissingCIVariable."""

import pytest

from canary_gitlab.reporter import MissingCIVariable
from canary_gitlab.reporter import MergeRequest
from canary_gitlab.reporter import escape_md
from canary_gitlab.reporter import escape_table_cell
from canary_gitlab.reporter import group_failed_jobs


# ---------------------------------------------------------------------------
# escape_table_cell
# ---------------------------------------------------------------------------


def test_escape_table_cell_plain():
    assert escape_table_cell("hello") == "hello"


def test_escape_table_cell_pipe():
    assert escape_table_cell("a|b") == r"a\|b"


def test_escape_table_cell_backslash():
    assert escape_table_cell("a\\b") == r"a\\b"


def test_escape_table_cell_newline():
    assert escape_table_cell("a\nb") == "a<br>b"


def test_escape_table_cell_carriage_return():
    assert escape_table_cell("a\rb") == "ab"


def test_escape_table_cell_non_string():
    assert escape_table_cell(42) == "42"


# ---------------------------------------------------------------------------
# escape_md
# ---------------------------------------------------------------------------


def test_escape_md_plain():
    assert escape_md("hello world") == "hello world"


def test_escape_md_backtick():
    assert escape_md("a`b") == r"a\`b"


def test_escape_md_backslash():
    assert escape_md("a\\b") == r"a\\b"


def test_escape_md_newline():
    assert escape_md("a\nb") == "a b"


def test_escape_md_non_string():
    assert escape_md(3.14) == "3.14"


# ---------------------------------------------------------------------------
# group_failed_jobs
# ---------------------------------------------------------------------------


class _FakeStatus:
    def __init__(self, success, outcome_name="FAILED"):
        self._success = success

        class _Outcome:
            name = outcome_name

        self.outcome = _Outcome()

    def is_success(self):
        return self._success


class _FakeJob:
    def __init__(self, name, success=False, outcome="FAILED"):
        self._name = name
        self.status = _FakeStatus(success, outcome)

    def display_name(self):
        return self._name


def test_group_failed_jobs_empty():
    assert group_failed_jobs([]) == {}


def test_group_failed_jobs_all_pass():
    jobs = [_FakeJob("a", success=True), _FakeJob("b", success=True)]
    assert group_failed_jobs(jobs) == {}


def test_group_failed_jobs_single_failure():
    jobs = [_FakeJob("test1", success=False, outcome="FAILED")]
    result = group_failed_jobs(jobs)
    assert "FAILED" in result
    assert len(result["FAILED"]) == 1


def test_group_failed_jobs_mixed():
    jobs = [
        _FakeJob("a", success=True),
        _FakeJob("b", success=False, outcome="FAILED"),
        _FakeJob("c", success=False, outcome="TIMEOUT"),
    ]
    result = group_failed_jobs(jobs)
    assert "FAILED" in result
    assert "TIMEOUT" in result
    assert len(result["FAILED"]) == 1
    assert len(result["TIMEOUT"]) == 1


def test_group_failed_jobs_groups_by_outcome():
    jobs = [
        _FakeJob("b1", success=False, outcome="FAILED"),
        _FakeJob("b2", success=False, outcome="FAILED"),
    ]
    result = group_failed_jobs(jobs)
    assert len(result["FAILED"]) == 2


# ---------------------------------------------------------------------------
# MergeRequest — MissingCIVariable paths
# ---------------------------------------------------------------------------


def test_merge_request_raises_without_gitlab_ci(monkeypatch):
    monkeypatch.delenv("GITLAB_CI", raising=False)
    with pytest.raises(MissingCIVariable, match="GITLAB_CI"):
        MergeRequest()


def test_merge_request_raises_without_token(monkeypatch):
    monkeypatch.setenv("GITLAB_CI", "true")
    monkeypatch.delenv("GITLAB_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ACCESS_TOKEN", raising=False)
    with pytest.raises(MissingCIVariable, match="GITLAB_ACCESS_TOKEN"):
        MergeRequest(access_token=None)


def test_merge_request_raises_without_mr_iid(monkeypatch):
    monkeypatch.setenv("GITLAB_CI", "true")
    monkeypatch.setenv("ACCESS_TOKEN", "tok")
    monkeypatch.delenv("CI_MERGE_REQUEST_IID", raising=False)
    with pytest.raises(MissingCIVariable, match="CI_MERGE_REQUEST_IID"):
        MergeRequest()


def test_merge_request_raises_without_project_id(monkeypatch):
    monkeypatch.setenv("GITLAB_CI", "true")
    monkeypatch.setenv("ACCESS_TOKEN", "tok")
    monkeypatch.setenv("CI_MERGE_REQUEST_IID", "1")
    monkeypatch.delenv("CI_PROJECT_ID", raising=False)
    with pytest.raises(MissingCIVariable, match="CI_PROJECT_ID"):
        MergeRequest()


def test_merge_request_raises_without_api_url(monkeypatch):
    monkeypatch.setenv("GITLAB_CI", "true")
    monkeypatch.setenv("ACCESS_TOKEN", "tok")
    monkeypatch.setenv("CI_MERGE_REQUEST_IID", "1")
    monkeypatch.setenv("CI_PROJECT_ID", "99")
    monkeypatch.delenv("CI_API_V4_URL", raising=False)
    with pytest.raises(MissingCIVariable, match="CI_API_V4_URL"):
        MergeRequest()
