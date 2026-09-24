# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for _canary.plugins.hooks — alias expansion, html report, summary formatters."""

from _canary.plugins.hooks import generate_html_report
from _canary.plugins.hooks import get_canary_prefix
from _canary.plugins.hooks import job_finish_summary
from _canary.plugins.hooks import job_start_summary

# ---------------------------------------------------------------------------
# get_canary_prefix
# ---------------------------------------------------------------------------


def test_get_canary_prefix_returns_path():
    """canary is installed in the venv, so this should return a Path."""
    from pathlib import Path

    result = get_canary_prefix()
    assert result is not None
    assert isinstance(result, Path)


def test_get_canary_prefix_returns_none_when_missing(monkeypatch):
    import importlib.util

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    result = get_canary_prefix()
    assert result is None


# ---------------------------------------------------------------------------
# generate_html_report — mock Session/Job objects
# ---------------------------------------------------------------------------


class _FakeTimekeeper:
    def duration(self):
        return 1.23


class _FakeCategory:
    def __init__(self, title):
        self._title = title

    def title(self):
        return self._title


class _FakeStatus:
    def __init__(self, category_title="Pass", display="PASSED"):
        self.category = _FakeCategory(category_title)
        self._display = display

    def display_name(self, style=None):
        return self._display


class _FakeJob:
    def __init__(self, name="mytest", status_title="Pass", status_display="PASSED", duration=1.0):
        self._name = name
        self._status_title = status_title
        self._status_display = status_display
        self.timekeeper = type("TK", (), {"duration": lambda self: duration})()
        self.status = _FakeStatus(status_title, status_display)

    def display_name(self, resolve=False):
        return self._name


class _FakeSession:
    def __init__(self, jobs):
        self.jobs = jobs


def test_generate_html_report_basic():
    session = _FakeSession([_FakeJob("test1"), _FakeJob("test2")])
    html = generate_html_report(session)
    assert "<html>" in html
    assert "test1" in html
    assert "test2" in html


def test_generate_html_report_is_valid_html():
    session = _FakeSession([])
    html = generate_html_report(session)
    assert html.startswith("<html>")
    assert "</html>" in html


def test_generate_html_report_contains_table_headers():
    session = _FakeSession([])
    html = generate_html_report(session)
    assert "<th>Test</th>" in html
    assert "<th>Status</th>" in html
    assert "<th>Duration</th>" in html


def test_generate_html_report_multiple_status_groups():
    jobs = [_FakeJob("pass_test", "Pass", "PASSED"), _FakeJob("fail_test", "Fail", "FAILED")]
    session = _FakeSession(jobs)
    html = generate_html_report(session)
    assert "pass_test" in html
    assert "fail_test" in html


def test_generate_html_report_empty_session():
    html = generate_html_report(_FakeSession([]))
    assert "<table>" in html


# ---------------------------------------------------------------------------
# job_start_summary / job_finish_summary
# ---------------------------------------------------------------------------


class _SummaryFakeStatus:
    def display_name(self):
        return "FAILED"


class _SummaryJob:
    def __init__(self, jid="abc1234", name="my.test"):
        self.id = jid
        self._name = name
        self.status = _SummaryFakeStatus()

    def display_name(self, resolve=False):
        return self._name


def test_job_start_summary_contains_job_id(monkeypatch):
    monkeypatch.delenv("GITLAB_CI", raising=False)
    # Ensure logging level is INFO so the summary is generated
    from _canary.util import logging as clog

    monkeypatch.setattr(clog, "get_level", lambda: clog.INFO)
    job = _SummaryJob(jid="abcdef1234", name="my.test")
    result = job_start_summary(job)
    assert "abcdef1" in result
    assert "my.test" in result


def test_job_start_summary_contains_timestamp_in_ci(monkeypatch):
    monkeypatch.setenv("GITLAB_CI", "true")
    from _canary.util import logging as clog

    monkeypatch.setattr(clog, "get_level", lambda: clog.INFO)
    job = _SummaryJob()
    result = job_start_summary(job)
    # CI mode prepends a timestamp like [2024.01.01 12:00:00]
    assert "[" in result and "]" in result


def test_job_start_summary_empty_when_log_level_high(monkeypatch):
    monkeypatch.delenv("GITLAB_CI", raising=False)
    from _canary.util import logging as clog

    monkeypatch.setattr(clog, "get_level", lambda: clog.WARNING)
    job = _SummaryJob()
    assert job_start_summary(job) == ""


def test_job_finish_summary_contains_attempt(monkeypatch):
    monkeypatch.delenv("GITLAB_CI", raising=False)
    from _canary.util import logging as clog

    monkeypatch.setattr(clog, "get_level", lambda: clog.INFO)
    job = _SummaryJob(jid="abcdef1234", name="my.test")
    result = job_finish_summary(job, attempt=2)
    assert "attempt 3" in result  # attempt+1
    assert "abcdef1" in result


def test_job_finish_summary_empty_when_log_level_high(monkeypatch):
    monkeypatch.delenv("GITLAB_CI", raising=False)
    from _canary.util import logging as clog

    monkeypatch.setattr(clog, "get_level", lambda: clog.WARNING)
    job = _SummaryJob()
    assert job_finish_summary(job, attempt=0) == ""


# ---------------------------------------------------------------------------
# canary_cmdline_parse alias expansion (via the actual hook function)
# ---------------------------------------------------------------------------


def test_alias_expansion_no_aliases():
    """With no aliases configured, parse_args is called directly."""
    import argparse

    import _canary.config
    from _canary.plugins.hooks import canary_cmdline_parse

    with _canary.config.override():
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        sub.add_parser("run")
        result = canary_cmdline_parse(parser=parser, args=["run"])
        assert result.command == "run"


def test_alias_expansion_with_alias(monkeypatch):
    """Alias is expanded before parsing."""
    import argparse

    import _canary.config
    from _canary.plugins.hooks import canary_cmdline_parse

    with _canary.config.override() as cfg:
        cfg.set("aliases", {"r": "run"})
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        sub.add_parser("run")
        result = canary_cmdline_parse(parser=parser, args=["r"])
        assert result.command == "run"


def test_alias_expansion_with_dollar_at(monkeypatch):
    """$@ passes remaining args into expansion."""
    import argparse

    import _canary.config
    from _canary.plugins.hooks import canary_cmdline_parse

    with _canary.config.override() as cfg:
        cfg.set("aliases", {"rw": "run $@"})
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        p_run = sub.add_parser("run")
        p_run.add_argument("--extra", default=None)
        result = canary_cmdline_parse(parser=parser, args=["rw", "--extra=hello"])
        assert result.command == "run"
        assert result.extra == "hello"
