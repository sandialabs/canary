# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Canary plugin system.

The pluggy-based extension machinery: the hook specifications
(:mod:`~_canary.plugins.hookspec`), the built-in hook implementations
(:mod:`~_canary.plugins.hooks`), the plugin manager that discovers and
registers plugins (:mod:`~_canary.plugins.pluginmanager`), and the built-in
``canaryconf`` fixture plugin (:mod:`~_canary.plugins.canaryconf_impl`).  The
public ``canary.hookimpl``/``canary.hookspec`` decorators and
``canary.CanaryPluginManager`` are re-exported from here.
"""
