# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Canary workspace layer.

The application aggregate that ties the pipeline together:
:class:`~_canary.workspace.workspace.Workspace` orchestrates collection,
selection, and running, and :class:`~_canary.workspace.session.Session` is the
per-run manifest.  This layer is the gateway between the CLI/app facade and the
domain (:mod:`_canary.core`), execution engine (:mod:`_canary.execution`), and
persistence (:mod:`_canary.persistence`).

``Workspace`` is a facade.  It owns the on-disk layout, lifecycle (create, load,
remove, detach), views and archiving, and delegates the pipeline stages to:

* :mod:`~_canary.workspace.locator`: functions that find a workspace on disk.
* :mod:`~_canary.workspace.collection`: :func:`collect_specs`, which scans paths
  for generators and caches the resolved specs in the database.
* :mod:`~_canary.workspace.selection`: :class:`SpecSelector`, which filters specs
  and manages selection tags.
* :mod:`~_canary.workspace.reconstruction`: :class:`JobReconstructor`, which turns
  specs and stored results back into a :class:`~_canary.core.job.Job` graph.
* :mod:`~_canary.workspace.runner`: :class:`SessionRunner`, which prepares a
  session (``prepare()``) and executes it (``execute()``).
"""
