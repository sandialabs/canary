import os
import re
import shutil
import subprocess
import sys
from typing import Optional


def cpu_count(default: int = 4) -> int:
    """Determine the number of processors on the current machine.
    Returns the 'default' if the probes fail.
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


def read_lscpu() -> Optional[int]:
    """"""
    if lscpu := shutil.which("lscpu"):
        try:
            args = [lscpu]
            output = subprocess.check_output(args, encoding="utf-8")
        except subprocess.CalledProcessError:
            return None
        else:
            sockets: Optional[int] = None
            cores_per_socket: Optional[int] = None
            for line in output.split("\n"):
                if line.startswith("Core(s) per socket:"):
                    cores_per_socket = int(line.split(":")[1])
                elif line.startswith("Socket(s):"):
                    sockets = int(line.split(":")[1])
            if cores_per_socket is not None and sockets is not None:
                cpu_count = cores_per_socket * sockets
                return None if cpu_count < 1 else cpu_count
    return None


def read_cpuinfo() -> Optional[int]:
    """
    count the number of lines of this pattern:

        processor       : <integer>
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


def read_sysctl() -> Optional[int]:
    if sysctl := shutil.which("sysctl"):
        try:
            args = [sysctl, "-n", "hw.physicalcpu"]
            output = subprocess.check_output(args, encoding="utf-8")
        except subprocess.CalledProcessError:
            return None
        else:
            return int(output)
    return None
