# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

# adapted from lib/spack/spack/util/module.py

import os
import subprocess
from contextlib import contextmanager
from typing import Generator
from typing import MutableMapping

# awk script alternative to posix `env -0`
awk_cmd = r"""awk 'BEGIN{for(name in ENVIRON) printf("%s=%s%c", name, ENVIRON[name], 0)}'"""


def _module(*args, environb: MutableMapping | None = None) -> str | None:
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
        )

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
        )
        return str(module_p.communicate()[0].decode())


def unload(modulename: str) -> None:
    _module("unload", modulename)


def purge() -> None:
    _module("purge")


def use(path: str) -> None:
    _module("use", path)


def load(modulename: str) -> None:
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
    pass
