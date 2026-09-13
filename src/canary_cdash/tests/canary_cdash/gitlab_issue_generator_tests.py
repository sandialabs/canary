# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for canary_cdash.gitlab_issue_generator — pure functions and mock-repo paths."""

import pytest

from canary_cdash.gitlab_issue_generator import close_test_issues_missing_from_cdash
from canary_cdash.gitlab_issue_generator import create_new_issue
from canary_cdash.gitlab_issue_generator import create_or_update_test_issues
from canary_cdash.gitlab_issue_generator import find_existing_issue
from canary_cdash.gitlab_issue_generator import generate_test_issue
from canary_cdash.gitlab_issue_generator import groupby_status_and_testname
from canary_cdash.gitlab_issue_generator import is_test_issue
from canary_cdash.gitlab_issue_generator import site_label
from canary_cdash.gitlab_issue_generator import test_status_label as make_status_label

# ---------------------------------------------------------------------------
# test_status_label / site_label
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status, expected",
    [
        ("Diffed", "test::diffed"),
        ("Failed", "test::failed"),
        ("Timeout", "test::timeout"),
        ("Unknown", "test::failed"),  # fallback
        ("whatever", "test::failed"),  # fallback
    ],
)
def test_test_status_label(status, expected):
    assert make_status_label(status) == expected


def test_site_label():
    assert site_label("node1") == "system: node1"
    assert site_label("my-cluster") == "system: my-cluster"


# ---------------------------------------------------------------------------
# is_test_issue
# ---------------------------------------------------------------------------


def test_is_test_issue_true():
    issue = {"labels": ["test::failed", "Stage::To Do"]}
    assert is_test_issue(issue) is True


def test_is_test_issue_false_no_test_label():
    issue = {"labels": ["Stage::To Do"]}
    assert is_test_issue(issue) is False


def test_is_test_issue_blacklisted_excluded():
    issue = {"labels": ["test::blacklisted", "test::failed"]}
    assert is_test_issue(issue, include_blacklisted=False) is False


def test_is_test_issue_blacklisted_included():
    issue = {"labels": ["test::blacklisted", "test::failed"]}
    assert is_test_issue(issue, include_blacklisted=True) is True


# ---------------------------------------------------------------------------
# groupby_status_and_testname
# ---------------------------------------------------------------------------


def _make_test(name, details, **kwargs):
    t = {"name": name, "details": details, "site": "s1", "details_link": "http://x"}
    t.update(kwargs)
    return t


def test_groupby_empty():
    assert groupby_status_and_testname([]) == {}


def test_groupby_failed():
    tests = [_make_test("mytest.py", "Completed (Failed)")]
    result = groupby_status_and_testname(tests)
    assert "Failed" in result
    assert "mytest" in result["Failed"]


def test_groupby_timeout():
    tests = [_make_test("mytest.py", "Timeout (Timeout)")]
    result = groupby_status_and_testname(tests)
    assert "Timeout" in result


def test_groupby_diffed():
    tests = [_make_test("mytest.py", "Completed (Diffed)")]
    result = groupby_status_and_testname(tests)
    assert "Diffed" in result


def test_groupby_unknown_details():
    tests = [_make_test("mytest.py", "Something Else")]
    result = groupby_status_and_testname(tests)
    assert "Unknown" in result


def test_groupby_bracket_name_stripped():
    tests = [_make_test("mytest[0].py", "Completed (Failed)")]
    result = groupby_status_and_testname(tests)
    # name becomes "mytest" (split at '[')
    assert "mytest" in result["Failed"]


def test_groupby_dot_name_stripped():
    tests = [_make_test("suite.mytest", "Completed (Failed)")]
    result = groupby_status_and_testname(tests)
    assert "suite" in result["Failed"]


def test_groupby_multiple_realizations():
    tests = [
        _make_test("mytest.py", "Completed (Failed)", site="s1"),
        _make_test("mytest.py", "Completed (Failed)", site="s2"),
    ]
    result = groupby_status_and_testname(tests)
    assert len(result["Failed"]["mytest"]) == 2


# ---------------------------------------------------------------------------
# generate_test_issue
# ---------------------------------------------------------------------------


def _make_realization(name="mytest", site="node1", fail_reason="Failed"):
    return {
        "name": name,
        "site": site,
        "fail_reason": fail_reason,
        "details_link": "http://cdash/test/1",
        "build_type": "Release",
        "compilername": "gcc",
        "compilerversion": "11.0",
    }


def test_generate_test_issue_basic():
    realizations = [_make_realization()]
    issue = generate_test_issue("mytest", realizations)
    assert issue["name"] == "mytest"
    assert issue["fail_reason"] == "Failed"
    assert "mytest" in issue["title"]
    assert "Failed" in issue["description"]


def test_generate_test_issue_legacy_title():
    realizations = [_make_realization(fail_reason="Timeout")]
    issue = generate_test_issue("t", realizations)
    assert issue["legacy_title"] == "TEST TIMEOUT: t"


def test_generate_test_issue_with_script():
    r = _make_realization()
    r["script"] = "http://gitlab/project/-/blob/main/tests/mytest.py"
    issue = generate_test_issue("mytest", [r])
    assert "mytest.py" in issue["description"]


def test_generate_test_issue_notes_contains_site():
    realizations = [_make_realization(site="supercluster")]
    issue = generate_test_issue("mytest", realizations)
    assert "supercluster" in issue["notes"]


def test_generate_test_issue_sites_list():
    realizations = [_make_realization(site="s1"), _make_realization(site="s2")]
    issue = generate_test_issue("mytest", realizations)
    assert "s1" in issue["sites"]
    assert "s2" in issue["sites"]


# ---------------------------------------------------------------------------
# find_existing_issue
# ---------------------------------------------------------------------------


def test_find_existing_issue_by_title():
    new_issue = {
        "title": "mytest: Failed",
        "legacy_title": "TEST FAILED: mytest",
        "fail_reason": "Failed",
    }
    existing = [{"title": "mytest: Failed", "labels": ["test::failed"], "iid": 1}]
    result = find_existing_issue(new_issue, existing)
    assert result is not None
    assert result["iid"] == 1


def test_find_existing_issue_by_legacy_title():
    new_issue = {
        "title": "mytest: Failed",
        "legacy_title": "TEST FAILED: mytest",
        "fail_reason": "Failed",
    }
    existing = [{"title": "TEST FAILED: mytest", "labels": ["test::failed"], "iid": 2}]
    result = find_existing_issue(new_issue, existing)
    assert result is not None
    assert result["iid"] == 2


def test_find_existing_issue_not_found():
    new_issue = {
        "title": "mytest: Failed",
        "legacy_title": "TEST FAILED: mytest",
        "fail_reason": "Failed",
    }
    existing = [{"title": "othertest: Failed", "labels": ["test::failed"], "iid": 99}]
    result = find_existing_issue(new_issue, existing)
    assert result is None


def test_find_existing_issue_label_mismatch():
    # Label doesn't match fail_reason → not found
    new_issue = {
        "title": "mytest: Timeout",
        "legacy_title": "TEST TIMEOUT: mytest",
        "fail_reason": "Timeout",
    }
    existing = [{"title": "mytest: Timeout", "labels": ["test::failed"], "iid": 5}]
    result = find_existing_issue(new_issue, existing)
    assert result is None


# ---------------------------------------------------------------------------
# Mock repo helpers
# ---------------------------------------------------------------------------


class MockRepo:
    def __init__(self, existing_issues=None):
        self._issues = existing_issues or []
        self.created = []
        self.edited = []

    def issues(self):
        return self._issues

    def new_issue(self, data):
        self._issues.append(
            {
                **data,
                "iid": len(self._issues) + 100,
                "state": "opened",
                "labels": data.get("labels", "").split(","),
            }
        )
        self.created.append(data)
        return len(self._issues) + 100

    def edit_issue(self, iid, data=None, notes=None):
        self.edited.append({"iid": iid, "data": data, "notes": notes})


# ---------------------------------------------------------------------------
# create_new_issue
# ---------------------------------------------------------------------------


def test_create_new_issue_calls_repo():
    repo = MockRepo()
    issue_data = {
        "title": "mytest: Failed",
        "fail_reason": "Failed",
        "description": "desc",
        "notes": "notes",
        "sites": ["node1"],
    }
    create_new_issue(repo, issue_data)
    assert len(repo.created) == 1
    assert repo.created[0]["title"] == "mytest: Failed"


# ---------------------------------------------------------------------------
# create_or_update_test_issues
# ---------------------------------------------------------------------------


def test_create_or_update_creates_when_no_existing():
    repo = MockRepo()
    issue_data = {
        "title": "t: Failed",
        "legacy_title": "TEST FAILED: t",
        "fail_reason": "Failed",
        "description": "d",
        "notes": "n",
        "sites": [],
    }
    create_or_update_test_issues(repo, issue_data)
    assert len(repo.created) == 1


def test_create_or_update_updates_when_existing():
    existing = [{"title": "t: Failed", "labels": ["test::failed"], "iid": 1, "state": "opened"}]
    repo = MockRepo(existing_issues=existing)
    issue_data = {
        "title": "t: Failed",
        "legacy_title": "TEST FAILED: t",
        "fail_reason": "Failed",
        "description": "d",
        "notes": "n",
        "sites": [],
    }
    create_or_update_test_issues(repo, issue_data)
    assert len(repo.edited) > 0


# ---------------------------------------------------------------------------
# close_test_issues_missing_from_cdash
# ---------------------------------------------------------------------------


def test_close_missing_closes_open_issues_not_in_current():
    existing = [{"title": "stale: Failed", "labels": ["test::failed"], "iid": 1, "state": "opened"}]
    repo = MockRepo(existing_issues=existing)
    current_issues = []  # nothing current → stale should be closed
    close_test_issues_missing_from_cdash(repo, current_issues)
    assert len(repo.edited) == 1
    assert repo.edited[0]["data"]["state_event"] == "close"


def test_close_missing_does_not_close_already_closed():
    existing = [{"title": "old: Failed", "labels": ["test::failed"], "iid": 2, "state": "closed"}]
    repo = MockRepo(existing_issues=existing)
    close_test_issues_missing_from_cdash(repo, [])
    assert len(repo.edited) == 0


def test_close_missing_does_not_close_current_issues():
    existing = [
        {"title": "current: Failed", "labels": ["test::failed"], "iid": 3, "state": "opened"}
    ]
    repo = MockRepo(existing_issues=existing)
    current = [{"title": "current: Failed", "legacy_title": "TEST FAILED: current"}]
    close_test_issues_missing_from_cdash(repo, current)
    assert len(repo.edited) == 0
