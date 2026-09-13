# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for _canary.util.rprobe — physical CPU count probes."""

import shutil
import subprocess

import pytest

import _canary.util.rprobe as rprobe_mod
from _canary.util.rprobe import cpu_count
from _canary.util.rprobe import read_lscpu
from _canary.util.rprobe import read_sysctl

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_cpu_count_cache():
    """cpu_count is @functools.cache — must clear between tests."""
    yield
    cpu_count.cache_clear()


LSCPU_SAMPLE = """\
Architecture:            x86_64
CPU(s):                  16
Thread(s) per core:      2
Core(s) per socket:      4
Socket(s):               2
NUMA node(s):            1
"""

LSCPU_SINGLE_SOCKET = """\
Core(s) per socket:      6
Socket(s):               1
"""

CPUINFO_HT = """\
processor\t: 0
siblings\t: 4
cpu cores\t: 2

processor\t: 1
siblings\t: 4
cpu cores\t: 2

processor\t: 2
siblings\t: 4
cpu cores\t: 2

processor\t: 3
siblings\t: 4
cpu cores\t: 2
"""

CPUINFO_NO_HT = """\
processor\t: 0
processor\t: 1
processor\t: 2
processor\t: 3
"""


# ---------------------------------------------------------------------------
# read_lscpu
# ---------------------------------------------------------------------------


def test_read_lscpu_parses_cores_times_sockets(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda exe: f"/usr/bin/{exe}")
    monkeypatch.setattr(subprocess, "check_output", lambda args, encoding: LSCPU_SAMPLE)
    result = read_lscpu()
    assert result == 8  # 4 cores/socket * 2 sockets


def test_read_lscpu_single_socket(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda exe: f"/usr/bin/{exe}")
    monkeypatch.setattr(subprocess, "check_output", lambda args, encoding: LSCPU_SINGLE_SOCKET)
    result = read_lscpu()
    assert result == 6


def test_read_lscpu_returns_none_when_not_found(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda exe: None)
    assert read_lscpu() is None


def test_read_lscpu_returns_none_on_error(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda exe: "/usr/bin/lscpu")
    monkeypatch.setattr(
        subprocess,
        "check_output",
        lambda args, encoding: (_ for _ in ()).throw(subprocess.CalledProcessError(1, "lscpu")),
    )
    assert read_lscpu() is None


def test_read_lscpu_returns_none_when_missing_fields(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda exe: "/usr/bin/lscpu")
    monkeypatch.setattr(subprocess, "check_output", lambda args, encoding: "Architecture: x86_64\n")
    assert read_lscpu() is None


# ---------------------------------------------------------------------------
# read_cpuinfo
# ---------------------------------------------------------------------------


def test_read_cpuinfo_with_hyperthreading(tmp_path, monkeypatch):
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text(CPUINFO_HT)
    import builtins

    import _canary.util.rprobe as rp

    original_exists = rp.os.path.exists
    monkeypatch.setattr(
        rp.os.path, "exists", lambda p: True if p == "/proc/cpuinfo" else original_exists(p)
    )

    real_open = builtins.open

    def fake_open(path, *args, **kwargs):
        if path == "/proc/cpuinfo":
            return real_open(str(cpuinfo), *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)

    result = rprobe_mod.read_cpuinfo()
    # 4 processors, siblings=4, cores=2 → factor=4//2=2 → 4//2 = 2
    assert result == 2


def test_read_cpuinfo_no_hyperthreading(tmp_path, monkeypatch):
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text(CPUINFO_NO_HT)
    import builtins

    import _canary.util.rprobe as rp

    original_exists = rp.os.path.exists

    monkeypatch.setattr(
        rp.os.path, "exists", lambda p: True if p == "/proc/cpuinfo" else original_exists(p)
    )

    def fake_open(path, *args, **kwargs):
        if path == "/proc/cpuinfo":
            return cpuinfo.open(*args, **kwargs)
        return builtins.open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)

    result = rprobe_mod.read_cpuinfo()
    assert result == 4


def test_read_cpuinfo_returns_none_when_file_absent(monkeypatch):
    import _canary.util.rprobe as rp

    monkeypatch.setattr(rp.os.path, "exists", lambda p: False)
    assert rprobe_mod.read_cpuinfo() is None


# ---------------------------------------------------------------------------
# read_sysctl
# ---------------------------------------------------------------------------


def test_read_sysctl_parses_output(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda exe: f"/usr/sbin/{exe}")
    monkeypatch.setattr(subprocess, "check_output", lambda args, encoding: "12\n")
    result = read_sysctl()
    assert result == 12


def test_read_sysctl_returns_none_when_not_found(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda exe: None)
    assert read_sysctl() is None


def test_read_sysctl_returns_none_on_error(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda exe: "/usr/sbin/sysctl")
    monkeypatch.setattr(
        subprocess,
        "check_output",
        lambda args, encoding: (_ for _ in ()).throw(subprocess.CalledProcessError(1, "sysctl")),
    )
    assert read_sysctl() is None


# ---------------------------------------------------------------------------
# cpu_count
# ---------------------------------------------------------------------------


def test_cpu_count_uses_lscpu_on_linux(monkeypatch):
    monkeypatch.setattr(rprobe_mod.sys, "platform", "linux")
    monkeypatch.setattr(rprobe_mod, "read_lscpu", lambda: 8)
    monkeypatch.setattr(rprobe_mod, "read_cpuinfo", lambda: 4)
    assert cpu_count() == 8


def test_cpu_count_falls_back_to_cpuinfo(monkeypatch):
    monkeypatch.setattr(rprobe_mod.sys, "platform", "linux")
    monkeypatch.setattr(rprobe_mod, "read_lscpu", lambda: None)
    monkeypatch.setattr(rprobe_mod, "read_cpuinfo", lambda: 4)
    assert cpu_count() == 4


def test_cpu_count_default_when_all_fail(monkeypatch):
    monkeypatch.setattr(rprobe_mod.sys, "platform", "linux")
    monkeypatch.setattr(rprobe_mod, "read_lscpu", lambda: None)
    monkeypatch.setattr(rprobe_mod, "read_cpuinfo", lambda: None)
    assert cpu_count(default=99) == 99


def test_cpu_count_darwin_tries_sysctl_first(monkeypatch):
    monkeypatch.setattr(rprobe_mod.sys, "platform", "darwin")
    monkeypatch.setattr(rprobe_mod, "read_sysctl", lambda: 10)
    monkeypatch.setattr(rprobe_mod, "read_lscpu", lambda: 8)
    assert cpu_count() == 10


def test_cpu_count_darwin_falls_back_to_lscpu(monkeypatch):
    monkeypatch.setattr(rprobe_mod.sys, "platform", "darwin")
    monkeypatch.setattr(rprobe_mod, "read_sysctl", lambda: None)
    monkeypatch.setattr(rprobe_mod, "read_lscpu", lambda: 6)
    assert cpu_count() == 6
