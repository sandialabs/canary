# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for canary_dist.status — resource pool status renderer."""

import io
import sys

import pytest

import canary_dist.status as status_mod
from canary_dist.status import color
from canary_dist.status import green
from canary_dist.status import print_resource_pool_status
from canary_dist.status import red
from canary_dist.status import yellow


# ---------------------------------------------------------------------------
# color helpers
# ---------------------------------------------------------------------------


def test_color_no_ansi_when_not_tty(monkeypatch):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    assert color("hello", "32") == "hello"


def test_color_ansi_when_tty(monkeypatch):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    result = color("hello", "32")
    assert "\033[32m" in result
    assert "hello" in result
    assert "\033[0m" in result


def test_green_red_yellow_delegates_to_color(monkeypatch):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    assert green("x") == "x"
    assert red("x") == "x"
    assert yellow("x") == "x"


# ---------------------------------------------------------------------------
# print_resource_pool_status — helper: StringIO + non-tty
# ---------------------------------------------------------------------------


@pytest.fixture()
def buf(monkeypatch):
    """Return a StringIO buffer and disable ANSI for predictable output."""
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    return io.StringIO()


SAMPLE_DATA = {
    "machines": [
        {
            "hostname": "node1",
            "tags": ["gpu"],
            "resources": {
                "cpus": [
                    {"id": "cpu0", "slots": 4},
                    {"id": "cpu1", "slots": 0},
                ],
                "gpus": [
                    {"id": "gpu0", "slots": 1},
                ],
            },
        }
    ]
}


def test_header_printed(buf):
    print_resource_pool_status(SAMPLE_DATA, file=buf)
    out = buf.getvalue()
    assert "Distributed Resource Pool" in out


def test_separator_line_printed(buf):
    print_resource_pool_status(SAMPLE_DATA, file=buf)
    out = buf.getvalue()
    assert "-" * 10 in out  # at least some dashes


def test_cluster_totals_printed(buf):
    print_resource_pool_status(SAMPLE_DATA, file=buf)
    out = buf.getvalue()
    assert "Cluster totals" in out
    assert "cpus: total=4" in out
    assert "gpus: total=1" in out


def test_host_name_printed(buf):
    print_resource_pool_status(SAMPLE_DATA, file=buf)
    assert "node1" in buf.getvalue()


def test_tags_printed(buf):
    print_resource_pool_status(SAMPLE_DATA, file=buf)
    assert "gpu" in buf.getvalue()


def test_no_resources_machine(buf):
    data = {"machines": [{"hostname": "empty", "tags": [], "resources": {}}]}
    print_resource_pool_status(data, file=buf)
    assert "(no resources)" in buf.getvalue()


def test_empty_machines_list(buf):
    print_resource_pool_status({"machines": []}, file=buf)
    out = buf.getvalue()
    # Should still print header and separator, just no machine details
    assert "Distributed Resource Pool" in out
    assert "Cluster totals" not in out


def test_verbose_shows_resource_ids(buf):
    print_resource_pool_status(SAMPLE_DATA, verbose=True, file=buf)
    out = buf.getvalue()
    assert "cpu0" in out
    assert "gpu0" in out


def test_verbose_false_hides_resource_ids(buf):
    print_resource_pool_status(SAMPLE_DATA, verbose=False, file=buf)
    out = buf.getvalue()
    # ids only appear in verbose mode
    assert "cpu0" not in out
    assert "gpu0" not in out


def test_groups_printed_when_present(buf):
    data = {
        "machines": [
            {
                "hostname": "n1",
                "tags": [],
                "groups": ["team-a", "team-b"],
                "resources": {},
            }
        ]
    }
    print_resource_pool_status(data, file=buf)
    assert "team-a" in buf.getvalue()
    assert "team-b" in buf.getvalue()


def test_groups_omitted_when_absent(buf):
    data = {
        "machines": [
            {"hostname": "n1", "tags": [], "resources": {}}
        ]
    }
    print_resource_pool_status(data, file=buf)
    assert "groups:" not in buf.getvalue()


def test_availability_percentage(buf):
    # 4 slots, 4 available → 100%
    data = {
        "machines": [
            {
                "hostname": "full",
                "tags": [],
                "resources": {
                    "cpus": [{"id": "c0", "slots": 4}]
                },
            }
        ]
    }
    print_resource_pool_status(data, file=buf)
    assert "100%" in buf.getvalue()


def test_zero_available_percentage(buf):
    data = {
        "machines": [
            {
                "hostname": "busy",
                "tags": [],
                "resources": {
                    "cpus": [{"id": "c0", "slots": 0}]
                },
            }
        ]
    }
    print_resource_pool_status(data, file=buf)
    assert "0%" in buf.getvalue()
