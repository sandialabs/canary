# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Canary plugin system.

The pluggy-based extension machinery: the hook specifications
(:mod:`~_canary.plugins.hookspec`), the built-in hook implementations
(:mod:`~_canary.plugins.hooks`), the plugin manager that discovers and
registers plugins (:mod:`~_canary.plugins.pluginmanager`), and the built-in
``canaryconf`` fixture plugin (:mod:`~_canary.plugins.canaryconf_impl`).

Normal project-local hook modules can be loaded explicitly with ``-p`` or by
the single-module autoload convention: ``./canaryhooks.py`` in the invocation
directory, or an importable ``canaryhooks`` module on ``PYTHONPATH``.  This is
distinct from ``canaryconf.py``, which implements directory-scoped setup and
teardown fixtures rather than general pluggy plugin loading.  The
public ``canary.hookimpl``/``canary.hookspec`` decorators and
``canary.CanaryPluginManager`` are re-exported from here.
"""
