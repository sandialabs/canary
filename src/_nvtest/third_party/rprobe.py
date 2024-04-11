#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.
import os
import re
import sys

from ..util.executable import Executable
from ..util.filesystem import which


def cpu_count(default=4):
    """Determine the number of processors on the current machine.
    Returns the 'default' if the probes fail.
    """
    mx = None
    if sys.platform == "darwin":
        mx = read_sysctl()
        if mx is None:
            mx = read_lscpu()
    else:
        mx = read_lscpu()
        if mx is None:
            mx = read_proccpuinfo()
    if not mx or mx < 1:
        mx = default

    return mx


def read_lscpu(default=4):
    """"""
    if not which("lscpu"):
        return None
    lscpu = Executable("lscpu")
    out = lscpu(output=str, fail_on_error=False)
    cores_per_socket, sockets = default, 1
    if lscpu.returncode == 0:
        for line in out.split("\n"):
            if line.startswith("Core(s) per socket:"):
                cores_per_socket = int(line.split(":")[1])
            elif line.startswith("Socket(s):"):
                sockets = int(line.split(":")[1])
    return cores_per_socket * sockets


def read_proccpuinfo():
    """
    count the number of lines of this pattern:

        processor       : <integer>
    """
    file = "/proc/cpuinfo"
    if os.path.exists(file):
        proc = re.compile("processor\s*:")
        sibs = re.compile("siblings\s*:")
        cores = re.compile("cpu cores\s*:")
        with open(file, "rt") as fp:
            num_sibs = 0
            num_cores = 0
            cnt = 0
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


def read_sysctl():
    if which("sysctl"):
        sysctl = Executable("sysctl")
        out = sysctl("-n", "hw.physicalcpu", output=str, fail_on_error=False)
        if sysctl.returncode == 0:
            return int(out.strip())
    return None
