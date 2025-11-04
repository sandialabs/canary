# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT


import psutil

from . import logging

logger = logging.get_logger(__name__)


def cpu_count(logical: bool | None = None) -> int:
    from .. import config  # lazy import to avoid circular deps

    if logical is None:
        logical = config.getoption("resource_pool_enable_hyperthreads", False)
    count = psutil.cpu_count(logical=logical)
    if count is None:
        raise RuntimeError("Unable to determine the number of CPUs")
    return count


def kill_process_tree(proc: psutil.Process | None) -> None:
    """kill a process tree rooted by `proc`"""
    if proc is None:
        return

    logger.debug(f"Killing process tree (root={proc.pid})")
    for child in proc.children(recursive=True):
        try:
            child.kill()
            logger.debug(f"--> killed child process ({child.pid}, root={proc.pid})")
        except psutil.NoSuchProcess:
            pass
    try:
        proc.kill()
    except psutil.NoSuchProcess as e:
        logger.debug(f"--> root process already finished ({e.pid})")
