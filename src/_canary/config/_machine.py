# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os


def system_config() -> dict:
    """Return machine specific configuration data.

    The values are taken directly from ``os.uname()``; canary does not model
    the OS/distribution beyond what the kernel reports.
    """
    uname = os.uname()
    return {
        "sysname": uname.sysname,
        "nodename": uname.nodename,
        "release": uname.release,
        "version": uname.version,
        "machine": uname.machine,
    }
