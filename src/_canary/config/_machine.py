# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import platform
import re
import sys
from typing import Any

from ..util.rprobe import cpu_count
from . import linux
from . import macos


def system_config() -> dict:
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
        login_no = re.search(r"-login(?P<n>\d+).*", sitename)
        if login_no:
            sitename = sitename.split("-login")[0] + login_no.group("n").zfill(2)
        else:
            sitename = sitename.replace("-login", "")
    config = dict(
        node=nodename,
        arch=uname.machine,
        site=sitename,
        host=sitename,
        name=os.getenv("SNLCLUSTER", uname.node),
        platform=uname.system,
        os=os_config,
    )
    return config


def machine_config() -> dict[str, Any]:
    return dict(gpu_count=0, cpu_count=cpu_count())
