# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Characterization of the public :mod:`canary` contract.

Pins the set of names ``import canary`` exposes and requires each to actually
resolve, making the public surface an enforced boundary so :mod:`_canary` can be
reorganized without silently breaking users or extension authors.

Changing the public API is a deliberate act: update
:data:`EXPECTED_PUBLIC_NAMES` and the extension/API documentation together.  A
failure here that was not intended means an accidental exposure or regression --
fix the implementation, not the test.
"""

import canary

# The authoritative set of names ``import canary`` is contracted to expose.
# Compared against ``canary.__all__``; every entry must also resolve.
# ``graph`` was intentionally removed (it never resolved); its two real
# callsites use ``canary.print_spec_graph`` instead.

EXPECTED_PUBLIC_NAMES = frozenset(
    {
        # test-script runtime API (eager)
        "config",
        "status",
        "enums",
        "directives",
        "patterns",
        "schema",
        "TestDiffed",
        "TestFailed",
        "TestSkipped",
        "centered_parameter_space",
        "list_parameter_space",
        "random_parameter_space",
        # domain / spec / job objects
        "BaseJob",
        "Job",
        "TestCase",
        "JobSpec",
        "JobSpecIR",
        "ResolvedSpec",
        "DependencySelector",
        "Artifact",
        "Asset",
        "Mask",
        # test-instance user-facing DTOs
        "TestInstance",
        "TestMultiInstance",
        "MissingTestInstance",
        # generators
        "AbstractSpecGenerator",
        "AbstractTestGenerator",
        "Generator",
        # selection / rules
        "Selector",
        "RuntimeSelector",
        "Rule",
        "RuntimeRule",
        "RuleOutcome",
        # plugin / extension author API
        "hookimpl",
        "hookspec",
        "CanaryPluginManager",
        "CanarySubcommand",
        "CanaryReporter",
        "Parser",
        "Config",
        # execution / launchers
        "Launcher",
        "SubprocessLauncher",
        "Runner",
        "Collector",
        # application / embedding API
        "app",
        "Session",
        "Workspace",
        "NotAWorkspaceError",
        "ViewSettings",
        # CLI entry point
        "console_main",
        # rendering / graph helper
        "print_spec_graph",
        # utility modules re-exported for convenience
        "color",
        "difflib",
        "filesystem",
        "logging",
        "module",
        "shell",
        "string",
        "time",
        "Executable",
        # version
        "version",
        "version_info",
    }
)


def test_all_matches_expected_public_names():
    """``canary.__all__`` must equal the frozen public surface (catches drift both ways)."""
    actual = set(canary.__all__)
    added = actual - EXPECTED_PUBLIC_NAMES
    removed = EXPECTED_PUBLIC_NAMES - actual
    assert not added, f"unexpected new public names in canary.__all__: {sorted(added)}"
    assert not removed, f"public names missing from canary.__all__: {sorted(removed)}"


def test_every_public_name_resolves():
    """Every name in ``canary.__all__`` must be accessible (eager or via ``__getattr__``).

    A name that raises is a broken contract -- the defect ``graph`` embodied.
    """
    unresolved = {}
    for name in canary.__all__:
        try:
            getattr(canary, name)
        except Exception as exc:  # noqa: BLE001 - report any failure
            unresolved[name] = repr(exc)
    assert not unresolved, f"public names failed to resolve: {unresolved}"


def test_graph_is_not_public():
    assert "graph" not in canary.__all__
    assert not hasattr(canary, "graph")


def test_print_spec_graph_is_public_and_callable():
    assert "print_spec_graph" in canary.__all__
    assert callable(canary.print_spec_graph)
