# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for canary_gitlab.gitlab — pure/isolated functions."""

import pytest

from canary_gitlab.gitlab import api_access_required
from canary_gitlab.gitlab import repo

# ---------------------------------------------------------------------------
# repo.sanitize_url
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, expected",
    [
        # git@ SSH syntax
        ("git@gitlab.example.com:group/project", "gitlab.example.com/group/project"),
        ("git@gitlab.example.com:group/project.git", "gitlab.example.com/group/project"),
        # https syntax
        ("https://gitlab.example.com/group/project", "gitlab.example.com/group/project"),
        ("https://gitlab.example.com/group/project.git", "gitlab.example.com/group/project"),
        # already plain (no prefix)
        ("gitlab.example.com/group/project", "gitlab.example.com/group/project"),
        # strip .git only
        ("gitlab.example.com/group/project.git", "gitlab.example.com/group/project"),
    ],
)
def test_sanitize_url(url, expected):
    assert repo.sanitize_url(url) == expected


# ---------------------------------------------------------------------------
# repo.__init__ / repr / str / gitlab_id
# ---------------------------------------------------------------------------


def test_repo_init_basic(monkeypatch):
    monkeypatch.delenv("ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("CI_PROJECT_ID", raising=False)
    monkeypatch.delenv("CI_API_V4_URL", raising=False)
    r = repo(
        url="https://gitlab.example.com/group/proj",
        access_token="tok",  # nosec B106
        project_id=42,
        api_url="http://api",
    )
    assert "gitlab.example.com/group/proj" in repr(r)
    assert r.gitlab_id == 42


def test_repo_init_requires_url_or_path():
    with pytest.raises((TypeError, ValueError)):
        repo(url=None, path=None)


def test_repo_build_api_url_no_query():
    r = repo(
        url="https://gitlab.example.com/g/p",
        api_url="http://api/v4",
        access_token="t",  # nosec B106
        project_id=1,
    )
    assert r.build_api_url(path="projects/1/issues") == "http://api/v4/projects/1/issues"


def test_repo_build_api_url_with_query():
    r = repo(
        url="https://gitlab.example.com/g/p",
        api_url="http://api/v4",
        access_token="t",  # nosec B106
        project_id=1,
    )
    url = r.build_api_url(path="projects/1/issues", query="state=opened")
    assert url == "http://api/v4/projects/1/issues?state=opened"


def test_repo_cloned_false_when_no_path():
    r = repo(url="https://gitlab.example.com/g/p")
    assert r.cloned() is False


def test_repo_cloned_true_when_path_set(tmp_path):
    r = repo(url="https://gitlab.example.com/g/p", path=str(tmp_path))
    assert r.cloned() is True


# ---------------------------------------------------------------------------
# api_access_required decorator
# ---------------------------------------------------------------------------


class _FakeRepo:
    """Minimal class to test the api_access_required decorator."""

    name = "FakeRepo"

    def __init__(self, *, access_token, gitlab_id, api_url):
        self.access_token = access_token
        self.gitlab_id = gitlab_id
        self.api_url = api_url

    @api_access_required
    def do_api_call(self):
        return "ok"


def test_api_access_required_passes_with_all_fields():
    obj = _FakeRepo(access_token="tok", gitlab_id=1, api_url="http://api")  # nosec B106
    assert obj.do_api_call() == "ok"


def test_api_access_required_raises_without_token():
    obj = _FakeRepo(access_token=None, gitlab_id=1, api_url="http://api")
    with pytest.raises(ValueError, match="access_token"):
        obj.do_api_call()


def test_api_access_required_raises_without_id():
    obj = _FakeRepo(access_token="tok", gitlab_id=None, api_url="http://api")  # nosec B106
    with pytest.raises(ValueError, match="project or group id"):
        obj.do_api_call()


def test_api_access_required_raises_without_api_url():
    obj = _FakeRepo(access_token="tok", gitlab_id=1, api_url=None)  # nosec B106
    with pytest.raises(ValueError, match="api url"):
        obj.do_api_call()


# ---------------------------------------------------------------------------
# repo.clone_url
# ---------------------------------------------------------------------------


def test_clone_url_https():
    r = repo(url="https://gitlab.example.com/group/project")
    assert r.clone_url("https") == "https://gitlab.example.com/group/project"


def test_clone_url_git():
    r = repo(url="https://gitlab.example.com/group/project")
    result = r.clone_url("git")
    assert result.startswith("git@")
    assert "group" in result
    assert "project" in result


def test_clone_url_invalid_protocol():
    r = repo(url="https://gitlab.example.com/group/project")
    with pytest.raises(ValueError, match="Unrecognized protocol"):
        r.clone_url("ftp")
