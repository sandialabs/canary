# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Sub-test registry and auto-runner for ``.pyt`` files.

A single ``.pyt`` file can define several named test instances.  Historically
this was done by calling :func:`canary_pyt.directives.name` once per instance
and then hand-writing a ``test()`` dispatcher plus an
``if __name__ == "__main__"`` guard that inspects ``get_instance().name``.

This module provides sugar for that pattern:

.. code-block:: python

    import canary
    import canary_pyt

    @canary_pyt.instance_test
    def test_foo(inst: canary.TestInstance) -> int:
        ...
        return 0

    @canary_pyt.instance_test
    def test_bar(inst):
        ...

There is no need to call :func:`canary_pyt.directives.name` or to write a
``test()``/``__main__`` block.  Each decorated function:

1. registers a test instance whose family name is the function name with a
   leading ``test_`` stripped (``test_foo`` -> ``foo``), and
2. is dispatched automatically at run time based on the running instance's
   family, receiving the read-only :class:`canary.TestInstance` as its only
   argument.

The decorated function should return an integer exit code (``0`` for success),
or raise one of the ``canary`` test-outcome exceptions
(:class:`canary.TestFailed`, ``TestDiffed``, ``TestSkipped``) which carry their
own exit codes.
"""

import atexit
import os
import sys
from typing import Any
from typing import Callable

import canary_pyt

__all__ = ["instance_test", "run_instance_tests", "registered_instance_tests"]

InstanceTestFunc = Callable[..., int | None]

# Registry of family-name -> function for the module currently being loaded /
# executed.  A .pyt file is loaded (for collection) and executed (at run time)
# in fresh interpreter states, so a module-global registry is safe: it is only
# ever populated by the single file under (load|execution).
_REGISTRY: dict[str, InstanceTestFunc] = {}

# Guard so the auto-runner's atexit hook is installed at most once and runs at
# most once.
_runner_installed = False
_runner_ran = False


def _instance_name(func: InstanceTestFunc) -> str:
    name = getattr(func, "__name__", "")
    if name.startswith("test_"):
        name = name[len("test_") :]
    if not name:
        raise ValueError(
            f"instance_test function {getattr(func, '__name__', func)!r} has an empty "
            "instance name after stripping the 'test_' prefix"
        )
    return name


def instance_test(func: InstanceTestFunc) -> InstanceTestFunc:
    """Register *func* as a named test instance and enable auto-dispatch.

    The family name is ``func.__name__`` with a leading ``test_`` removed.  The
    decorator emits the equivalent of ``canary_pyt.directives.name(<family>)``
    so the instance is discovered during test collection, and installs a
    run-time dispatcher (once) that calls the matching function for the running
    instance.

    Args:
        func: A callable taking the running :class:`canary.TestInstance` and
            returning an integer exit code (or ``None``, treated as ``0``).

    Returns:
        The original *func*, unmodified, so it can still be called directly.
    """
    name = _instance_name(func)
    if name in _REGISTRY:
        raise RuntimeError(f"Duplicate instance_test registration for {name!r}")
    _REGISTRY[name] = func

    # Emit the family directive.  During collection ``canary_pyt.directives`` is
    # monkeypatched to a recorder, so this registers the instance.  At run time
    # it is the real (no-op) directives module.
    canary_pyt.directives.name(name)

    _install_runner_if_needed()
    return func


def registered_instance_tests() -> dict[str, InstanceTestFunc]:
    """Return a copy of the family-name -> function registry."""
    return dict(_REGISTRY)


def reset_registry() -> None:
    """Clear the instance-test registry.

    Called at the start of each ``.pyt`` collection pass so registrations from a
    previously-loaded file (loaded in the same interpreter) do not leak into the
    next one and trigger spurious duplicate-registration errors.
    """
    global _runner_installed, _runner_ran
    _REGISTRY.clear()
    atexit.unregister(_atexit_runner)
    _runner_installed = False
    _runner_ran = False


def _install_runner_if_needed() -> None:
    """Install the run-time auto-dispatch hook exactly once.

    The hook is only installed when:

    * we are not collecting (``canary_pyt.FILE_SCANNING`` is False), and
    * the decorated function's module is the ``__main__`` script — i.e. the
      ``.pyt`` file is actually being executed by canary, not merely imported
      (e.g. by the test-suite or another module).

    This keeps the ``atexit``/``os._exit`` dispatch from firing in-process when
    the decorator is exercised outside a real run.
    """
    global _runner_installed
    if _runner_installed:
        return
    if canary_pyt.FILE_SCANNING:
        # Being loaded for collection; directives are recorded, tests never run.
        return
    if not _caller_is_main():
        return
    _runner_installed = True
    atexit.register(_atexit_runner)


def _caller_is_main() -> bool:
    """Return True when the code applying the decorator lives in ``__main__``."""
    frame = sys._getframe(1)
    # Walk out of this module's frames to the caller that used the decorator.
    while frame is not None and frame.f_globals.get("__name__") == __name__:
        frame = frame.f_back
    if frame is None:
        return False
    return frame.f_globals.get("__name__") == "__main__"


def _atexit_runner() -> None:
    """atexit shim that dispatches and forces the resulting exit code.

    ``atexit`` swallows :class:`SystemExit`, so to propagate the test's exit
    code we flush the standard streams and call :func:`os._exit` directly.  A
    ``.pyt`` file runs in a dedicated subprocess whose sole purpose is this
    test, so bypassing interpreter cleanup here is acceptable.
    """
    global _runner_ran
    if _runner_ran:
        return
    _runner_ran = True
    rc = run_instance_tests()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(rc)


def run_instance_tests(arg_path: Any = None) -> int:
    """Dispatch to the registered function for the running instance.

    Resolves the running instance via :func:`canary.get_instance`, looks up its
    family in the registry, calls it with the instance, and returns an integer
    exit code.  Test-outcome exceptions (``canary.TestFailed`` and friends) are
    translated to their carried ``exit_code``.

    Args:
        arg_path: Optional path passed through to :func:`canary.get_instance`.

    Returns:
        The integer exit code for the process.
    """
    import canary

    if not _REGISTRY:
        raise RuntimeError("No @canary_pyt.instance_test functions were registered")

    inst = canary.get_instance(arg_path)
    family = getattr(inst, "family", None)
    if family is None:
        raise RuntimeError("Unable to determine the running instance family")

    try:
        func = _REGISTRY[family]
    except KeyError:
        available = ", ".join(sorted(_REGISTRY))
        raise RuntimeError(
            f"No @canary_pyt.instance_test registered for {family!r}. Available: {available}"
        )

    try:
        rc = func(inst)
    except canary.TestFailed as e:
        return getattr(e, "exit_code", 1)
    except Exception as e:
        # Test-outcome exceptions (TestDiffed/TestSkipped/...) carry exit_code.
        exit_code = getattr(e, "exit_code", None)
        if exit_code is not None:
            return int(exit_code)
        raise
    return 0 if rc is None else int(rc)
