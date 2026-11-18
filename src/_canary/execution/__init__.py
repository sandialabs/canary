# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Canary execution layer.

The engine that turns jobs into running processes: OS launchers, the
resource-aware scheduling queue, the worker-pool executor, and the run-tests
driver.  Per-job work spaces are a domain type (:mod:`~_canary.core.execspace`).  These
modules perform I/O and manage subprocesses; the domain (:mod:`_canary.core`)
does not depend on them.
"""
