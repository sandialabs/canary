# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Canary workspace layer: the data.

:class:`~_canary.workspace.workspace.Workspace` is where things live and what is
stored: the on-disk layout, lifecycle (create, load, remove, detach), the results
database (``db``), views, archiving, and the read queries (``load_jobs``, ``find``,
``find_job``, ``find_jobspec``, ``find_specids``, ``info``, ``tag_info``).  It does
not collect, select or run; that is :class:`~_canary.engine.engine.Engine`.
:class:`~_canary.workspace.session.Session` is the manifest of one run.

* :mod:`~_canary.workspace.locator`: functions that find a workspace on disk.
* :mod:`~_canary.workspace.reconstruction`: :class:`JobReconstructor`, which turns
  stored specs and results back into a :class:`~_canary.core.job.Job` graph.
"""
