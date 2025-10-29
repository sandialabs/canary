# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT


import psutil


def cpu_count(logical: bool | None = None) -> int | None:
    from .. import config  # lazy import to avoid circular deps

    if logical is None:
        logical = config.getoption("resource_pool_enable_hyperthreads", False)
    return psutil.cpu_count(logical=logical)
