# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Public interface for the canary utility package.

Exposes ``cpu_count``, which queries ``psutil`` and respects the
``resource_pool_enable_hyperthreads`` configuration option to decide
whether to count logical (hyperthreaded) or physical cores.
"""

import psutil


def cpu_count(logical: bool | None = None) -> int:
    """Return the number of CPUs available to canary.

    Args:
        logical: If ``True``, count logical (hyperthreaded) CPUs; if ``False``,
            count physical cores only.  When ``None`` (default), the value is
            read from the ``resource_pool_enable_hyperthreads`` config option.

    Returns:
        CPU count as reported by ``psutil``.

    Raises:
        RuntimeError: If ``psutil`` cannot determine the CPU count.
    """
    from .. import config  # lazy import to avoid circular deps

    if logical is None:
        logical = config.getoption("resource_pool_enable_hyperthreads", False)
    count = psutil.cpu_count(logical=logical)
    if count is None:
        raise RuntimeError("Unable to determine the number of CPUs")
    return count
