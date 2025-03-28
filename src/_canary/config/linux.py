# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import re
import sys
from types import SimpleNamespace


def integer_or_str(x):
    try:
        return int(x)
    except Exception:
        return str(x)


def sys_info():
    if not sys.platform.startswith("linux"):
        return
    try:
        # This will throw an error if imported on a non-Linux platform.
        from ..third_party.distro import linux_distribution

        distname, version, _ = linux_distribution(full_distribution_name=False)
        vendor, version = str(distname), str(version)
    except ImportError:  # pragma: no cover
        vendor, version = "unknown", ""

    # Grabs major version from tuple on redhat; on other platforms
    # grab the first legal identifier in the version field.  On
    # debian you get things like 'wheezy/sid'; sid means unstable.
    # We just record 'wheezy' and don't get quite so detailed.
    version = re.split(r"[^\w-]", version)
    version_info = [integer_or_str(x) for x in version]
    if "ubuntu" in distname:  # pragma: no cover
        version_str = ".".join(version[0:2])
    else:
        version_str = version[0]

    return SimpleNamespace(
        vendor=vendor,
        version_info=version_info,
        version_str=version_str,
    )
