# adapted from lib/spack/spack/util/module.py

import os
import subprocess
from contextlib import contextmanager
from typing import Generator
from typing import MutableMapping
from typing import Optional

# awk script alternative to posix `env -0`
awk_cmd = r"""awk 'BEGIN{for(name in ENVIRON) printf("%s=%s%c", name, ENVIRON[name], 0)}'"""


def _module(*args, environb: Optional[MutableMapping] = None) -> Optional[str]:
    module_cmd = f"module {' '.join(args)}"
    environb = environb or os.environb

    if args[0] in ["load", "swap", "unload", "purge", "use", "unuse"]:
        # Suppress module output
        module_cmd += r" >/dev/null 2>&1; " + awk_cmd
        module_p = subprocess.Popen(
            module_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=True,
            executable="/bin/bash",
            env=environb,
        )

        new_environb = {}
        output = module_p.communicate()[0]

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


@contextmanager
def load(module_name: str, use: Optional[str] = None) -> Generator[None, None, None]:
    save_environb = dict(os.environb)
    if use is not None:
        existing_modulepath = os.getenv("MODULEPATH", "")
        os.environb[b"MODULEPATH"] = f"{use}:{existing_modulepath}".encode()
    text = _module("show", module_name).split()  # type: ignore
    for i, word in enumerate(text):
        if word == "conflict":
            _module("unload", text[i + 1])
    _module("load", module_name)
    yield
    os.environb.clear()
    os.environb.update(save_environb)


loaded = load
