# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Canary engine layer: the behaviour that acts on a workspace.

:class:`~_canary.engine.engine.Engine` is what ``app`` drives and the CLI/TUI attach
to.  It collects and selects specs, builds the jobs of a session, and runs it:
``prepare()`` builds the session, ``execute()`` owns the run-time state (result
listener, live view, :class:`~_canary.execution.context.ExecutionContext`) and
hands the jobs to the ``canary_runtests`` backends.  Backends see only the
context, never the workspace.

* :mod:`~_canary.engine.engine`: :class:`Engine`.
* :mod:`~_canary.engine.jobs`: :func:`construct_jobs`, which builds the jobs of
  a new session from specs and the latest stored results.
* :mod:`~_canary.engine.collection`: :func:`collect_specs`, which scans paths
  for generators and caches the resolved specs in the database.
* :mod:`~_canary.engine.selection`: :class:`SpecSelector`, which filters specs
  and saves selection tags.
"""
