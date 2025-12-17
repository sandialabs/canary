# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import glob
import importlib.resources
from pathlib import Path

import _canary.config as config
from _canary.util.filesystem import working_dir
from _canary.workspace import Workspace
from canary_hpc.conductor import CanaryHPCConductor


def test_repo_bfilter(tmpdir):
    root = Path(importlib.resources.files("canary"))
    examples = root / "examples"
    with working_dir(tmpdir.strpath, create=True):
        with config.override():
            config.options.canary_hpc_scheduler = "shell"
            # config.ioptions.canary_hpc_scheduler = "shell"
            spec = {"count": 2, "duration": None, "layout": "flat", "nodes": "any"}
            config.options.canary_hpc_batchspec = spec
            # config.ioptions.canary_hpc_batchspec = spec
            conductor = CanaryHPCConductor(backend="shell")
            config.pluginmanager.register(conductor, f"canary_hpc{conductor.backend.name}")
            workspace = Workspace.create("tests", force=True)
            specs = workspace.create_selection(
                "default", {str(examples / "basic"): [], str(examples / "vvt"): []}
            )
            workspace.run(specs)
            files = glob.glob(
                "tests/.canary/cache/canary-hpc/batches/**/canary-inp.sh",
                recursive=True,
            )
            assert len(files) == 2
