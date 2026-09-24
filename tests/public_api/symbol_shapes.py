# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Shape and relationship checks for load-bearing public :mod:`canary` symbols.

Complements ``all_surface.py`` (which pins the *set* of public names) by pinning
relationships a rename or refactor could silently break: the documented
compatibility aliases, the test-script exception types, the plugin decorators,
and the runtime lookup helpers.
"""

import canary


def test_documented_aliases_point_at_their_targets():
    assert canary.TestCase is canary.Job
    assert canary.ResolvedSpec is canary.JobSpec
    assert canary.AbstractTestGenerator is canary.AbstractSpecGenerator


def test_test_script_exceptions_are_exception_types():
    """Test scripts raise these to signal outcomes, so they must be exceptions."""
    for name in ("TestDiffed", "TestFailed", "TestSkipped"):
        cls = getattr(canary, name)
        assert isinstance(cls, type) and issubclass(cls, BaseException)


def test_plugin_hook_markers_are_callable():
    assert callable(canary.hookimpl)
    assert callable(canary.hookspec)


def test_parameter_space_markers_are_the_enum_members():
    """The top-level markers must be the same objects as ``canary.enums``."""
    for name in ("centered_parameter_space", "list_parameter_space", "random_parameter_space"):
        assert getattr(canary, name) is getattr(canary.enums, name)


def test_runtime_lookup_helpers_and_testcase_alias():
    """``get_instance``/``get_job`` are the in-script runtime API; pin them and the alias.

    They are module-level functions rather than ``__all__`` re-exports, but are a
    stable part of the contract used inside ``.pyt``/``.vvt`` scripts.
    """
    assert callable(canary.get_instance)
    assert callable(canary.get_job)
    assert canary.get_testcase is canary.get_job


def test_version_shape():
    assert isinstance(canary.version, str)
    assert isinstance(canary.version_info, tuple)
