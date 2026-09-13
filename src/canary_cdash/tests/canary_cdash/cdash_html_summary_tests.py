# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for canary_cdash.cdash_html_summary — pure functions and env-var paths."""

import os

import pytest

from canary_cdash.cdash_html_summary import MissingCIVariable
from canary_cdash.cdash_html_summary import _html_summary
from canary_cdash.cdash_html_summary import cdash_summary
from canary_cdash.cdash_html_summary import groupby_buildgroup


# ---------------------------------------------------------------------------
# groupby_buildgroup
# ---------------------------------------------------------------------------


def test_groupby_buildgroup_empty():
    assert groupby_buildgroup([]) == {}


def test_groupby_buildgroup_single():
    builds = [{"buildgroup": "Nightly", "buildname": "B1"}]
    result = groupby_buildgroup(builds)
    assert "Nightly" in result
    assert len(result["Nightly"]) == 1


def test_groupby_buildgroup_multiple_same_group():
    builds = [
        {"buildgroup": "Nightly", "buildname": "B1"},
        {"buildgroup": "Nightly", "buildname": "B2"},
    ]
    result = groupby_buildgroup(builds)
    assert len(result["Nightly"]) == 2


def test_groupby_buildgroup_multiple_groups():
    builds = [
        {"buildgroup": "Nightly", "buildname": "B1"},
        {"buildgroup": "Experimental", "buildname": "B2"},
        {"buildgroup": "Nightly", "buildname": "B3"},
    ]
    result = groupby_buildgroup(builds)
    assert len(result["Nightly"]) == 2
    assert len(result["Experimental"]) == 1


# ---------------------------------------------------------------------------
# _html_summary
# ---------------------------------------------------------------------------


def _make_build(
    id=1,
    site="mysite",
    siteid=10,
    unixtimestamp=0,
    buildname="mybuild",
    builddate="2024-01-01",
    time="30s",
    hasupdate=False,
    hasconfigure=False,
    hascompilation=False,
    hastest=False,
    **kwargs,
):
    b = dict(
        id=id,
        site=site,
        siteid=siteid,
        unixtimestamp=unixtimestamp,
        buildname=buildname,
        builddate=builddate,
        time=time,
        hasupdate=hasupdate,
        hasconfigure=hasconfigure,
        hascompilation=hascompilation,
        hastest=hastest,
    )
    b.update(kwargs)
    return b


def test_html_summary_empty_groups():
    html = _html_summary("http://cdash", "MyProject", {})
    assert "<html>" in html
    # title uses project.title() which capitalises "MyProject" → "Myproject"
    assert "Myproject" in html or "MyProject" in html


def test_html_summary_contains_buildgroup_header():
    build = _make_build()
    html = _html_summary("http://cdash", "MyProject", {"Nightly": [build]})
    assert "Nightly" in html


def test_html_summary_contains_build_name():
    build = _make_build(buildname="special-build")
    html = _html_summary("http://cdash", "MyProject", {"Nightly": [build]})
    assert "special-build" in html


def test_html_summary_hasupdate_true():
    build = _make_build(hasupdate=True, update={"files": 3})
    html = _html_summary("http://cdash", "MyProject", {"N": [build]})
    assert "viewUpdate.php" in html


def test_html_summary_hasupdate_false():
    build = _make_build(hasupdate=False)
    html = _html_summary("http://cdash", "MyProject", {"N": [build]})
    assert "None" in html


def test_html_summary_hasconfigure_true():
    build = _make_build(hasconfigure=True, configure={"error": 1, "warning": 2})
    html = _html_summary("http://cdash", "MyProject", {"N": [build]})
    assert "viewConfigure.php" in html


def test_html_summary_hasconfigure_false():
    build = _make_build(hasconfigure=False)
    html = _html_summary("http://cdash", "MyProject", {"N": [build]})
    assert "Missing" in html


def test_html_summary_hascompilation_true():
    build = _make_build(hascompilation=True, compilation={"error": 0, "warning": 1})
    html = _html_summary("http://cdash", "MyProject", {"N": [build]})
    assert "viewBuildError.php" in html


def test_html_summary_hastest_true():
    build = _make_build(
        hastest=True,
        test={"notrun": 0, "fail": 2, "pass": 10, "fail_timeout": 1, "fail_diff": 0, "fail_fail": 1},
    )
    html = _html_summary("http://cdash", "MyProject", {"N": [build]})
    assert "viewTest.php" in html
    assert "onlypassed" in html
    assert "onlyfailed" in html


def test_html_summary_hastest_false():
    build = _make_build(hastest=False)
    html = _html_summary("http://cdash", "MyProject", {"N": [build]})
    assert "<td colspan=5> Missing </td>" in html


def test_html_summary_is_valid_html():
    build = _make_build()
    html = _html_summary("http://cdash", "MyProject", {"N": [build]})
    assert html.startswith("<html>")
    assert html.strip().endswith("</html>")


# ---------------------------------------------------------------------------
# cdash_summary — env var paths
# ---------------------------------------------------------------------------


def test_cdash_summary_missing_cdash_url(monkeypatch):
    monkeypatch.delenv("CDASH_URL", raising=False)
    monkeypatch.delenv("CDASH_PROJECT", raising=False)
    with pytest.raises(MissingCIVariable):
        cdash_summary()


def test_cdash_summary_missing_cdash_project(monkeypatch):
    monkeypatch.setenv("CDASH_URL", "http://cdash.example.com")
    monkeypatch.delenv("CDASH_PROJECT", raising=False)
    with pytest.raises(MissingCIVariable):
        cdash_summary()


def test_cdash_summary_writes_file(tmp_path, monkeypatch):
    outfile = str(tmp_path / "summary.html")

    # Patch generate_cdash_html_summary to avoid real network calls
    monkeypatch.setattr(
        "canary_cdash.cdash_html_summary.generate_cdash_html_summary",
        lambda url, project, groups, skip_sites: "<html><body>test</body></html>",
    )

    cdash_summary(url="http://cdash", project="Test", file=outfile)
    assert os.path.exists(outfile)
    with open(outfile) as f:
        assert "test" in f.read()


def test_cdash_summary_writes_stdout_when_no_target(capsys, monkeypatch):
    monkeypatch.setattr(
        "canary_cdash.cdash_html_summary.generate_cdash_html_summary",
        lambda url, project, groups, skip_sites: "<html>output</html>",
    )
    cdash_summary(url="http://cdash", project="P")
    captured = capsys.readouterr()
    assert "output" in captured.out
