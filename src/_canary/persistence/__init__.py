# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Canary persistence layer.

The repository/DAO over the workspace SQLite database
(:mod:`~_canary.persistence.database`): the authoritative store for
cross-session state (specs, the dependency graph, selections, and results) and
the single-writer result spool.  Domain modules (:mod:`_canary.core`) do not
depend on this layer; application services reach the database through it.
"""
