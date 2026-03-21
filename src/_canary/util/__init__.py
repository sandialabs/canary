# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT


import psutil


def cpu_count(logical: bool | None = None) -> int:
    from .. import config  # lazy import to avoid circular deps

    if logical is None:
        logical = config.getoption("resource_pool_enable_hyperthreads", False)
    count = psutil.cpu_count(logical=logical)
    if count is None:
        raise RuntimeError("Unable to determine the number of CPUs")
    return count
