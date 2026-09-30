# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Canary execution layer.

The engine that turns jobs into running processes: per-job filesystem work
spaces (:mod:`~_canary.execution.testexec`), OS launchers, the resource-aware
scheduling queue, the worker-pool executor, and the run-tests driver.  These
modules perform I/O and manage subprocesses; the domain (:mod:`_canary.core`)
does not depend on them.
"""
