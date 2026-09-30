# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Canary session layer.

The application aggregate that ties the pipeline together:
:class:`~_canary.session.workspace.Workspace` orchestrates collection,
selection, and running, and :class:`~_canary.session.workspace.Session` is the
per-run manifest.  This layer is the gateway between the CLI/app facade and the
domain (:mod:`_canary.core`), execution engine (:mod:`_canary.execution`), and
persistence (:mod:`_canary.persistence`).
"""
