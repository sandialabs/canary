# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import platform
import sys
from types import SimpleNamespace

mac_releases = {
    "10.0": "cheetah",
    "10.1": "puma",
    "10.2": "jaguar",
    "10.3": "panther",
    "10.4": "tiger",
    "10.5": "leopard",
    "10.6": "snowleopard",
    "10.7": "lion",
    "10.8": "mountainlion",
    "10.9": "mavericks",
    "10.10": "yosemite",
    "10.11": "elcapitan",
    "10.12": "sierra",
    "10.13": "highsierra",
    "10.14": "mojave",
    "10.15": "catalina",
    "10.16": "bigsur",
    "10.17": "monterey",
}


def sys_info():
    if sys.platform != "darwin":
        return
    ver = platform.mac_ver()[0].split(".")
    macos_version = ".".join((ver[0], ver[1]))
    version_info = [int(x) for x in ver]
    return SimpleNamespace(
        vendor="apple",
        version_info=version_info,
        macos_version=macos_version,
        version_str=mac_releases.get(macos_version, "macos"),
    )
