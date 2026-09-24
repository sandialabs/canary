# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Directory-scoped setup/teardown via ``canaryconf.py`` sentinel files.

Overview
--------
When ``canaryconf.py`` is found anywhere in the test tree, canary scans it for
two well-known functions:

* ``canary_setup(ctx)``   — run *before* every test whose ``file_path`` is at
  or below the directory containing ``canaryconf.py``.
* ``canary_teardown(ctx)`` — run *after* every such test, even on failure.

Either function may be absent; a ``canaryconf.py`` defining only one of them is
valid.

Both functions receive the job's :class:`~_canary.testinst.TestInstance` as
``ctx``, the same object a test body receives via ``canary.get_instance()``.

Implementation notes
--------------------
The plugin hooks ``canary_generate_modifyitems`` *after* dependency resolution
has already run.  It:

1. Scans ``generator.specs`` for ``canaryconf.py`` files that happen to have
   been collected (they won't be — ``collect.py`` skips them — so we actually
   walk the filesystem for each unique ``(file_root, directory)`` pair present
   in the spec list).
2. For each ``canaryconf.py`` found, uses ``ast.parse`` to check whether
   ``canary_setup`` and/or ``canary_teardown`` are defined *without executing
   user code at generation time*.
3. Creates synthetic :class:`~_canary.core.jobspec.JobSpec` objects for setup and/or
   teardown.  These specs carry *no* ``command``: they are dispatched
   in-process by :class:`~_canary.execution.launcher.PythonFunctionLauncher`, which
   imports the ``canaryconf.py`` file and calls ``canary_setup(ctx)`` /
   ``canary_teardown(ctx)`` directly (see :mod:`_canary.execution.launcher`).  The
   synthetic spec's ``exec_path`` is set to a dedicated ``__setup__`` /
   ``__teardown__`` directory beneath the governing directory so the function
   runs in the session tree location mirroring the ``canaryconf.py``.
4. Wires :class:`~_canary.core.jobspec.SpecDependency` edges:
   - Every test in scope: ``test.dependencies += [SpecDependency(setup, "on_success")]``
   - Teardown spec: ``teardown.dependencies += [SpecDependency(test, "always")]``
     for every test in scope.
5. Appends the synthetic specs to ``generator.specs``.

Metadata
--------
Every synthetic spec carries an ``attributes["canary_conftest"]`` dict so that
reporters and future tooling can identify and handle these jobs specially:

.. code-block:: python

    spec.attributes["canary_conftest"] = {
        "role": "setup",          # or "teardown"
        "scope_dir": str(dir),    # absolute path of the governing directory
        "source_file": str(path), # absolute path to the canaryconf.py
    }

Additionally, the keyword ``"canary_conftest"`` is added to every synthetic
spec's keyword list so users can filter them immediately with
``canary status -k 'not canary_conftest'``.

Rerun behaviour
---------------
Synthetic specs have stable IDs (derived from ``family`` + ``file_root`` +
``file_path`` via :func:`~_canary.core.jobspec.build_spec_id`), identical to
regular jobs.  A setup job that passed in a previous session will therefore be
correctly skipped by ``--only not_pass`` or ``--only failed`` rerun strategies.
Teardown re-runs whenever any downstream test re-runs, because the
``when="always"`` edges make teardown unready until those tests finish.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

from .core.jobspec import JobSpec
from .core.jobspec import SpecDependency
from .hookspec import hookimpl
from .util import logging

if TYPE_CHECKING:
    from .generate import Generator

logger = logging.get_logger(__name__)

#: Sentinel filename that triggers setup/teardown injection.
CANARYCONF_FILENAME = "canaryconf.py"

#: Function names canary looks for inside the sentinel file.
SETUP_FUNCTION = "canary_setup"
TEARDOWN_FUNCTION = "canary_teardown"

#: Maps a synthetic job's ``role`` to the function invoked in the canaryconf.py.
ROLE_TO_FUNCTION = {"setup": SETUP_FUNCTION, "teardown": TEARDOWN_FUNCTION}

#: Keyword attached to every synthetic spec.
CONFTEST_KEYWORD = "canary_conftest"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _top_level_functions(source: str) -> set[str]:
    """Return the set of top-level function names defined in *source*.

    Uses ``ast.parse`` so user code is never executed at generation time.
    Returns an empty set on parse errors (the file may still be valid Python
    that imports things before defining functions — we accept false-negatives
    rather than crashing generation).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and isinstance(node.col_offset == 0, bool)
        # col_offset == 0 means top-level definition
        and node.col_offset == 0
    }


def _has_setup(source: str) -> bool:
    return SETUP_FUNCTION in _top_level_functions(source)


def _has_teardown(source: str) -> bool:
    return TEARDOWN_FUNCTION in _top_level_functions(source)


def _find_canaryconf(directory: Path) -> Path | None:
    """Return the ``canaryconf.py`` path in *directory*, or ``None``."""
    p = directory / CANARYCONF_FILENAME
    return p if p.is_file() else None


# ---------------------------------------------------------------------------
# spec factory
# ---------------------------------------------------------------------------


def _make_synthetic_spec(
    *, role: str, canaryconf_path: Path, file_root: Path, scope_dir: Path
) -> JobSpec:
    """Build a synthetic setup or teardown :class:`JobSpec`.

    The spec carries no ``command``.  It is dispatched in-process by
    :class:`~_canary.execution.launcher.PythonFunctionLauncher`, which imports the
    ``canaryconf.py`` file and calls the function named by ``role`` (see
    :data:`ROLE_TO_FUNCTION`) with the job's ``TestInstance`` as ``ctx``.

    Args:
        role:           ``"setup"`` or ``"teardown"``.
        canaryconf_path: Absolute path to the ``canaryconf.py`` file.
        file_root:      The ``file_root`` of the sibling test specs in scope.
        scope_dir:      Absolute path of the directory being governed.
    """
    file_path = canaryconf_path.relative_to(file_root)
    family = f"{CANARYCONF_FILENAME}::{role}"

    spec = JobSpec(
        file_root=file_root,
        file_path=file_path,
        family=family,
        # Execute in a dedicated per-role directory beneath the session tree
        # location mirroring the canaryconf.py's governing directory (e.g.
        # ``<scope_dir>/__setup__`` / ``<scope_dir>/__teardown__``).  A dedicated
        # directory is required because the job machinery creates and enters an
        # execution workspace; the governing directory itself is shared by the
        # governed tests and cannot be reused as an exec dir.
        exec_path=file_path.parent / f"__{role}__",
        keywords=[CONFTEST_KEYWORD, role],
        attributes={
            "canary_conftest": {
                "role": role,
                "scope_dir": str(scope_dir),
                "source_file": str(canaryconf_path),
            }
        },
    )
    return spec


# ---------------------------------------------------------------------------
# core injection logic
# ---------------------------------------------------------------------------


def _inject_conftest_jobs(generator: "Generator") -> None:
    """Scan the spec list for ``canaryconf.py`` files and inject synthetic jobs.

    Mutates ``generator.specs`` in place.
    """
    specs = generator.specs

    if not specs:
        return

    # Collect all unique (file_root, directory) pairs present in the spec list.
    # For each, walk up the directory tree to catch inherited canaryconf.py
    # files from ancestor directories (within file_root).
    # We use a dict keyed by canaryconf path → list[JobSpec] to map each
    # sentinel file to the specs it governs.
    conftest_to_specs: dict[Path, list[JobSpec]] = {}
    file_root_for_conftest: dict[Path, Path] = {}

    for spec in specs:
        # Skip specs that are themselves synthetic conftest jobs (safety guard
        # for future re-entrant calls).
        if "canary_conftest" in spec.attributes:
            continue

        test_dir = (spec.file_root / spec.file_path).parent
        # Walk from test_dir up to file_root, inclusive, looking for
        # canaryconf.py at each level.
        current = test_dir
        root = spec.file_root
        while True:
            if cf := _find_canaryconf(current):
                conftest_to_specs.setdefault(cf, []).append(spec)
                file_root_for_conftest[cf] = root
            if current == root:
                break
            parent = current.parent
            if not str(current).startswith(str(root)):
                break
            current = parent

    if not conftest_to_specs:
        return

    # Build the set of canaryconf.py paths already represented in the spec list
    # so that a second call (e.g. rerun, re-entrant hook) is idempotent.
    already_injected: set[str] = {
        spec.attributes["canary_conftest"]["source_file"]
        for spec in specs
        if "canary_conftest" in spec.attributes
    }

    new_specs: list[JobSpec] = []

    for cf_path, governed in conftest_to_specs.items():
        if str(cf_path) in already_injected:
            continue
        file_root = file_root_for_conftest[cf_path]
        scope_dir = cf_path.parent

        try:
            source = cf_path.read_text()
        except OSError as exc:
            logger.warning(f"canaryconf: could not read {cf_path}: {exc}")
            continue

        has_setup = _has_setup(source)
        has_teardown = _has_teardown(source)

        if not has_setup and not has_teardown:
            logger.debug(
                f"canaryconf: {cf_path} defines neither {SETUP_FUNCTION!r} "
                f"nor {TEARDOWN_FUNCTION!r} — ignoring"
            )
            continue

        logger.debug(
            f"canaryconf: {cf_path} governs {len(governed)} spec(s) "
            f"(setup={has_setup}, teardown={has_teardown})"
        )

        setup_spec: JobSpec | None = None
        teardown_spec: JobSpec | None = None

        if has_setup:
            setup_spec = _make_synthetic_spec(
                role="setup", canaryconf_path=cf_path, file_root=file_root, scope_dir=scope_dir
            )
            new_specs.append(setup_spec)

        if has_teardown:
            teardown_spec = _make_synthetic_spec(
                role="teardown", canaryconf_path=cf_path, file_root=file_root, scope_dir=scope_dir
            )
            new_specs.append(teardown_spec)

        # Wire dependency edges onto every governed test spec.
        for spec in governed:
            if setup_spec is not None:
                # Test must wait for setup to succeed.
                if setup_spec not in [d.spec for d in spec.dependencies]:
                    spec.dependencies.append(SpecDependency(spec=setup_spec, when="on_success"))

            if teardown_spec is not None:
                # Teardown must wait for the test to finish (regardless of outcome).
                if spec not in [d.spec for d in teardown_spec.dependencies]:
                    teardown_spec.dependencies.append(SpecDependency(spec=spec, when="always"))

    generator.specs = specs + new_specs


# ---------------------------------------------------------------------------
# plugin hook
# ---------------------------------------------------------------------------


@hookimpl
def canary_generate_modifyitems(generator: "Generator") -> None:
    """Inject setup/teardown jobs derived from ``canaryconf.py`` files."""
    _inject_conftest_jobs(generator)
