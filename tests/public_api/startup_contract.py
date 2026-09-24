# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""The ``import canary`` startup-latency contract.

Every ``.pyt``/``.vvt`` test runs in a subprocess that does ``import canary``,
so that import must stay cheap: the heavy CLI, execution, and persistence
modules are loaded lazily (via ``canary.__getattr__`` / ``_LAZY_IMPORTS``), not
eagerly.  ``canary/__init__.py`` maintains this split deliberately.

This test pins the split so the Phase 7 reorganization of ``_canary`` cannot
silently pull a heavy module onto the eager path and regress subprocess startup.
If a module legitimately moves eager/lazy, update the relevant set here together
with the change.
"""

import importlib
import sys

# Heavy implementation modules that must NOT be imported merely by ``import
# canary``.  Each is only needed by the CLI, the scheduler/executor, or
# persistence -- never by a test script at import time.
LAZY_ONLY_MODULES = frozenset(
    {
        "_canary.app",
        "_canary.main",
        "_canary.workspace",
        "_canary.database",
        "_canary.collect",
        "_canary.select",
        "_canary.execution.runtest",
        "_canary.execution.queue_executor",
        "_canary.reporters.reporter",
        "_canary.subcommands.run",
    }
)

# Modules a test script relies on at import time; these are expected eager so the
# lazy machinery never adds per-name overhead on the hot path.
EAGER_RUNTIME_MODULES = frozenset(
    {
        "_canary.config",
        "_canary.core.status",
        "_canary.core.error",
        "_canary.job",
        "_canary.core.jobspec",
        "_canary.testinst",
        "_canary.hookspec",
    }
)


def _fresh_import_canary():
    """Import ``canary`` from a clean module cache and return the new ``sys.modules``.

    Restores whatever was previously cached so later tests keep object identity
    with the live modules they imported at collection time.
    """
    tracked = [m for m in sys.modules if m == "canary" or m.startswith("_canary")]
    saved = {name: sys.modules[name] for name in tracked}
    try:
        for name in tracked:
            sys.modules.pop(name, None)
        importlib.import_module("canary")
        return set(sys.modules)
    finally:
        for name in tracked:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


def test_heavy_modules_stay_off_the_eager_import_path():
    loaded = _fresh_import_canary()
    leaked = sorted(LAZY_ONLY_MODULES & loaded)
    assert not leaked, f"import canary eagerly loaded lazy-only modules: {leaked}"


def test_runtime_modules_are_eager():
    """The in-script runtime modules must load with ``canary`` (no lazy penalty)."""
    loaded = _fresh_import_canary()
    missing = sorted(EAGER_RUNTIME_MODULES - loaded)
    assert not missing, f"expected eager runtime modules were not imported: {missing}"
