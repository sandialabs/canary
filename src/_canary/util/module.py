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
import subprocess
from contextlib import contextmanager
from typing import Generator
from typing import MutableMapping

# awk script alternative to posix `env -0`
awk_cmd = r"""awk 'BEGIN{for(name in ENVIRON) printf("%s=%s%c", name, ENVIRON[name], 0)}'"""


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
    module_cmd = f"module {' '.join(args)}"
    environb = environb or os.environb

    if args[0] in ["load", "swap", "unload", "purge", "use", "unuse"]:
        # Suppress module output
        module_cmd += r" >/dev/null 2>&1 && " + awk_cmd
        module_p = subprocess.Popen(
            module_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=True,
            executable="/bin/bash",
            env=environb,
        )  # nosec B602

        new_environb = {}
        module_p.wait()
        output = module_p.communicate()[0]
        if module_p.returncode != 0:
            raise ModuleError(f"failed: {module_cmd}: {output.decode()}")

        # Loop over each environment variable key=value byte string
        for entry in output.strip(b"\0").split(b"\0"):
            # Split variable name and value
            parts = entry.split(b"=", 1)
            if len(parts) != 2:
                continue
            new_environb[parts[0]] = parts[1]

        # Update os.environ with new dict
        environb.clear()
        environb.update(new_environb)  # novermin
        return None

    else:
        # Simply execute commands that don't change state and return output
        module_p = subprocess.Popen(
            module_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=True,
            executable="/bin/bash",
        )  # nosec B602
        return str(module_p.communicate()[0].decode())


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
    if use is not None:
        existing_modulepath = os.getenv("MODULEPATH", "")
        prepend_path = use if isinstance(use, str) else ":".join(use)
        os.environb[b"MODULEPATH"] = f"{prepend_path}:{existing_modulepath}".encode()
    try:
        save_environb = dict(os.environb)
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
