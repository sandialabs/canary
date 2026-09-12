# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for the canary_addoption hook.

Verifies that a plugin implementing canary_addoption can register CLI arguments
that are then available on the parsed namespace.
"""

import pluggy
import pytest

import canary

hookspec = pluggy.HookspecMarker("canary")
hookimpl = pluggy.HookimplMarker("canary")


class Spec:
    @hookspec
    def canary_addoption(self, parser) -> None:
        """Allow plugins to add CLI options."""


class Plugin:
    @hookimpl
    def canary_addoption(self, parser: canary.Parser) -> None:
        parser.add_plugin_argument(
            "--tolerance",
            help="Tolerance when analyzing results against a baseline",
            type=float,
            default=1e-8,
        )


def test_plugin_registered_argument_default_value() -> None:
    """A plugin-registered argument is present with its default after parsing []."""
    pm = pluggy.PluginManager("canary")
    pm.add_hookspecs(Spec)
    pm.register(Plugin())

    parser = canary.Parser()
    pm.hook.canary_addoption(parser=parser)

    ns = parser.parse_args([])
    assert ns.tolerance == pytest.approx(1e-8)


def test_plugin_registered_argument_accepts_override() -> None:
    """A plugin-registered argument accepts a value passed on the command line."""
    pm = pluggy.PluginManager("canary")
    pm.add_hookspecs(Spec)
    pm.register(Plugin())

    parser = canary.Parser()
    pm.hook.canary_addoption(parser=parser)

    ns = parser.parse_args(["--tolerance", "1e-6"])
    assert ns.tolerance == pytest.approx(1e-6)
