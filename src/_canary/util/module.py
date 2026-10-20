# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

# adapted from lib/spack/spack/util/module.py

"""Helpers for interacting with environment-modules (``module`` command).

Provides ``load``, ``unload``, ``purge``, ``use``, and the ``loaded`` context
manager, which temporarily activates one or more modules and restores the
original environment on exit.
"""

import os
import shlex
import subprocess
from contextlib import contextmanager
from typing import Generator
from typing import MutableMapping

# awk script alternative to posix `env -0`
awk_cmd = r"""awk 'BEGIN{for(name in ENVIRON) printf("%s=%s%c", name, ENVIRON[name], 0)}'"""

#: Default time limit (seconds) for a ``module`` command; override with
#: ``CANARY_MODULE_TIMEOUT``.
DEFAULT_MODULE_TIMEOUT = 300.0


def _module_timeout() -> float:
    try:
        return float(os.getenv("CANARY_MODULE_TIMEOUT", DEFAULT_MODULE_TIMEOUT))
    except ValueError:
        return DEFAULT_MODULE_TIMEOUT


def _run_module(cmd: str, env: MutableMapping | None) -> subprocess.CompletedProcess:
    """Run *cmd* through bash, reading output with ``communicate`` (no pipe deadlock)."""
    try:
        return subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=True,
            executable="/bin/bash",
            env=env,
            timeout=_module_timeout(),
            check=False,
        )  # nosec B602 - arguments are shlex-quoted
    except subprocess.TimeoutExpired:
        raise ModuleError(f"timed out after {_module_timeout():g} s: {cmd}") from None


def _module(*args, environb: MutableMapping | None = None) -> str | None:
    """Run a ``module`` sub-command, updating ``environb`` for state-changing commands.

    For commands that mutate environment state (``load``, ``swap``, ``unload``,
    ``purge``, ``use``, ``unuse``) the resulting environment is captured via awk
    and applied to ``environb``.  For read-only commands (e.g. ``show``) the
    subprocess stdout is returned as a string.

    Args:
        *args: Sub-command and arguments forwarded to the ``module`` shell function.
        environb: Mutable bytes environment mapping to update; defaults to ``os.environb``.

    Returns:
        Subprocess output as a string for read-only commands, or ``None`` for
        state-mutating commands.

    Raises:
        ModuleError: If a state-changing command exits with a non-zero status.
    """
    if not args:
        raise ModuleError("no module sub-command given")
    module_cmd = "module " + " ".join(shlex.quote(str(a)) for a in args)
    if environb is None:
        environb = os.environb

    if args[0] in ["load", "swap", "unload", "purge", "use", "unuse"]:
        # Suppress module output
        cp = _run_module(module_cmd + r" >/dev/null 2>&1 && " + awk_cmd, environb)
        output = cp.stdout or b""
        if cp.returncode != 0:
            raise ModuleError(f"failed: {module_cmd}: {output.decode('utf-8', errors='replace')}")

        new_environb = {}
        # Loop over each environment variable key=value byte string
        for entry in output.strip(b"\0").split(b"\0"):
            # Split variable name and value
            parts = entry.split(b"=", 1)
            if len(parts) != 2:
                continue
            new_environb[parts[0]] = parts[1]
        if not new_environb:
            raise ModuleError(f"failed: {module_cmd}: could not capture resulting environment")

        # Update os.environ with new dict
        environb.clear()
        environb.update(new_environb)  # novermin
        return None

    else:
        # Simply execute commands that don't change state and return output
        cp = _run_module(module_cmd, None)
        return (cp.stdout or b"").decode("utf-8", errors="replace")


def unload(modulename: str) -> None:
    """Unload an environment module.

    Args:
        modulename: Name of the module to unload.
    """
    _module("unload", modulename)


def purge() -> None:
    """Unload all currently loaded environment modules."""
    _module("purge")


def use(path: str) -> None:
    """Prepend ``path`` to ``MODULEPATH`` via ``module use``.

    Args:
        path: Directory to add to the module search path.
    """
    _module("use", path)


def load(modulename: str) -> None:
    """Load an environment module, resolving conflicts first.

    If the module declares conflicts, the conflicting modules are unloaded
    before loading ``modulename``.

    Args:
        modulename: Name of the module to load.
    """
    text = _module("show", modulename).split()  # type: ignore
    for i, word in enumerate(text):
        if word == "conflict":
            try:
                _module("unload", text[i + 1])
            except ModuleError:
                pass
    _module("load", modulename)


@contextmanager
def loaded(
    modulename: str, *names: str, use: str | list[str] | None = None
) -> Generator[None, None, None]:
    """Context manager that loads modules and restores the original environment on exit.

    Args:
        modulename: Primary module to load.
        *names: Additional modules to load after ``modulename``.
        use: Optional path or list of paths to prepend to ``MODULEPATH`` before loading.
    """
    # Snapshot *before* touching MODULEPATH so it is restored on exit too.
    save_environb = dict(os.environb)
    try:
        if use is not None:
            existing_modulepath = os.getenv("MODULEPATH", "")
            prepend_path = use if isinstance(use, str) else ":".join(use)
            os.environb[b"MODULEPATH"] = f"{prepend_path}:{existing_modulepath}".encode()
        for name in [modulename, *names]:
            text = _module("show", name).split()  # type: ignore
            for i, word in enumerate(text):
                if word == "conflict":
                    try:
                        _module("unload", text[i + 1])
                    except ModuleError:
                        pass
        for name in [modulename, *names]:
            _module("load", name)
        yield
    finally:
        os.environb.clear()
        os.environb.update(save_environb)


class ModuleError(Exception):
    """Raised when a ``module`` command exits with a non-zero status."""

    pass
