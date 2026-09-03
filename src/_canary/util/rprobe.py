# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Physical CPU count probes for Linux (lscpu, /proc/cpuinfo) and macOS (sysctl).

The main entry point is ``cpu_count()``, which tries each platform-appropriate
probe in order and falls back to a configurable default.
"""

import functools
import os
import re
import shutil
import subprocess
import sys


@functools.cache
def cpu_count(default: int = 4) -> int:
    """Determine the number of physical processors on the current machine.

    Tries ``lscpu`` and ``sysctl`` on macOS, ``lscpu`` and ``/proc/cpuinfo``
    on Linux.  Returns ``default`` if all probes fail.

    Args:
        default: Fallback value when no probe succeeds (default 4).

    Returns:
        Number of physical CPU cores.
    """
    if sys.platform == "darwin":
        if cpu_count := read_sysctl():
            return cpu_count
        elif cpu_count := read_lscpu():
            return cpu_count
    else:
        if cpu_count := read_lscpu():
            return cpu_count
        elif cpu_count := read_cpuinfo():
            return cpu_count
    return default


def read_lscpu() -> int | None:
    """Parse ``lscpu`` output to determine physical core count.

    Returns:
        Physical core count, or ``None`` if ``lscpu`` is unavailable or fails.
    """
    if lscpu := shutil.which("lscpu"):
        try:
            args = [lscpu]
            output = subprocess.check_output(args, encoding="utf-8")
        except subprocess.CalledProcessError:
            return None
        else:
            sockets: int | None = None
            cores_per_socket: int | None = None
            for line in output.split("\n"):
                if line.startswith("Core(s) per socket:"):
                    cores_per_socket = int(line.split(":")[1])
                elif line.startswith("Socket(s):"):
                    sockets = int(line.split(":")[1])
            if cores_per_socket is not None and sockets is not None:
                cpu_count = cores_per_socket * sockets
                return None if cpu_count < 1 else cpu_count
    return None


def read_cpuinfo() -> int | None:
    """Parse ``/proc/cpuinfo`` to determine physical core count.

    Accounts for hyperthreading by dividing total processor entries by the
    siblings-to-cores ratio when available.

    Returns:
        Physical core count, or ``None`` if the file is absent or unreadable.
    """
    file = "/proc/cpuinfo"
    if os.path.exists(file):
        proc = re.compile(r"processor\s*:")
        sibs = re.compile(r"siblings\s*:")
        cores = re.compile(r"cpu cores\s*:")
        with open(file, "rt") as fp:
            num_sibs: int = 0
            num_cores: int = 0
            cnt: int = 0
            for line in fp:
                if proc.match(line) is not None:
                    cnt += 1
                elif sibs.match(line) is not None:
                    num_sibs = int(line.split(":")[1])
                elif cores.match(line) is not None:
                    num_cores = int(line.split(":")[1])
            if cnt > 0:
                if num_sibs and num_cores and num_sibs > num_cores:
                    # eg, if num siblings is twice num cores, then physical
                    # cores is half the total processor count
                    fact = int(num_sibs // num_cores)
                    if fact > 0:
                        return cnt // fact
                return cnt
    return None


def read_sysctl() -> int | None:
    """Query ``sysctl hw.physicalcpu`` to determine physical core count on macOS.

    Returns:
        Physical core count, or ``None`` if ``sysctl`` is unavailable or fails.
    """
    if sysctl := shutil.which("sysctl"):
        try:
            args = [sysctl, "-n", "hw.physicalcpu"]
            output = subprocess.check_output(args, encoding="utf-8")
        except subprocess.CalledProcessError:
            return None
        else:
            return int(output)
    return None
