import os
import platform
import re
import sys

from ..third_party import rprobe
from ..util.executable import Executable
from ..util.filesystem import which
from . import linux
from . import macos

editable_properties = (
    "sockets_per_node",
    "cores_per_socket",
    "cpu_count",
    "device_count",
    "devices_per_socket",
)


def machine_config() -> dict:
    """Return machine specific configuration data"""
    if sys.platform == "darwin":
        info = macos.sys_info()
    elif sys.platform.startswith("linux"):
        info = linux.sys_info()
    else:
        raise ValueError(f"Unknown system {sys.platform}")
    vendor = info.vendor
    version_str = info.version_str
    uname = platform.uname()

    os_config = dict(
        vendor=vendor,
        version=version_str,
        name=f"{version_str}" if vendor == "apple" else f"{vendor}{version_str}",
        release=uname.release,
        fullversion=" ".join(uname),
    )

    nodename = uname.node
    sitename = nodename
    if "-login" in sitename:
        login_no = re.search("\-login(?P<n>\d+).*", sitename)
        if login_no:
            sitename = sitename.split("-login")[0] + login_no.group("n").zfill(2)
        else:
            sitename = sitename.replace("-login", "")
    ns = read_machine_info()
    config = dict(
        node=nodename,
        arch=uname.machine,
        site=sitename,
        host=sitename,
        name=os.getenv("SNLCLUSTER", uname.node),
        platform=uname.system,
        sockets_per_node=ns["sockets_per_node"],
        cores_per_socket=ns["cores_per_socket"],
        cpu_count=ns["cpu_count"],
        device_count=0,
        devices_per_socket=0,
        os=os_config,
    )
    return config


def read_machine_info() -> dict:
    info = dict(
        sockets_per_node=1,
        cores_per_socket=rprobe.cpu_count(),
        cpu_count=rprobe.cpu_count(),
    )
    if which("sinfo"):
        sinfo = Executable("sinfo")
        opts = [
            "%X",  # Number of sockets per node
            "%Y",  # Number of cores per socket
            "%Z",  # Number of threads per core
            "%c",  # Number of CPUs per node
            "%D",  # Number of nodes
        ]
        format = " ".join(opts)
        out = sinfo("-o", format, fail_on_error=False, output=str)
        sockets_per_node, cores_per_socket, _, cpus_per_node, node_count = out.split()
        info["sockets_per_node"] = sockets_per_node
        info["cores_per_socket"] = cores_per_socket
        info["cpu_count"] = cpus_per_node * node_count
    return info
