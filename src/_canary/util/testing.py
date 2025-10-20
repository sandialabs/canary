# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import subprocess
import sys
from typing import Any


class CanaryCommand:
    def __init__(self, command_name: str) -> None:
        self.command_name = command_name
        self.default_args: list[str] = []

    def add_default_args(self, *args: str) -> None:
        self.default_args.extend(args)

    def __call__(self, *args: str, **kwargs: Any) -> subprocess.CompletedProcess:
        env: dict[str, str] = {}
        if "env" in kwargs:
            env.update(kwargs.pop("env"))
        else:
            env.update(os.environ)
        env.pop("CANARYCFG64", None)
        env["CANARY_DISABLE_KB"] = "1"

        cpus: int = -1
        if "cpus" in kwargs:
            cpus = int(kwargs.pop("cpus"))
        if "_CANARY_TESTING_CPUS" in env:
            # Environment variable takes precedence
            cpus = int(env.pop("_CANARY_TESTING_CPUS"))

        gpus: int = -1
        if "gpus" in kwargs:
            gpus = int(kwargs.pop("gpus"))
        if "_CANARY_TESTING_GPUS" in env:
            # Environment variable takes precedence
            gpus = int(env.pop("_CANARY_TESTING_GPUS"))

        cmd: list[str] = [sys.executable, "-m", "canary"]
        if kwargs.pop("debug", False):
            cmd.append("-d")
        if cpus > 0:
            cmd.extend(["-c", f"resource_pool:cpus:{cpus}"])
        if gpus > 0:
            cmd.extend(["-c", f"resource_pool:gpus:{gpus}"])
        cmd.extend(self.default_args)
        cmd.append(self.command_name)
        cmd.extend(args)
        cp = subprocess.run(cmd, **kwargs)
        return cp
