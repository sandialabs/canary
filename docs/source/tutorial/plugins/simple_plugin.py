#!/usr/bin/env python3
"""Simple plugin example for tutorials."""


def canary_example_hook():
    """Example plugin hook that can be called during test execution."""
    print("Simple plugin hook executed!")
    return "plugin_result"


def canary_addhooks(pluginmanager):
    """Register our plugin hooks."""
    pluginmanager.add_hook("canary_example_hook", canary_example_hook)
