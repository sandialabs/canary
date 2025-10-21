# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import glob
import importlib.resources
from pathlib import Path

import _canary.config as config
import _canary.session as session
from _canary.util.filesystem import working_dir
from canary_hpc.conductor import CanaryHPCConductor


def test_session_bfilter(tmpdir):
    root = Path(importlib.resources.files("canary"))
    examples = root / "examples"
    with working_dir(tmpdir.strpath, create=True):
        with config.override():
            config.pluginmanager.hook.canary_addhooks(pluginmanager=config.pluginmanager)
            config.options.canary_hpc_scheduler = "shell"
            config.ioptions.canary_hpc_scheduler = "shell"
            spec = {"count": 2, "duration": None, "layout": "flat", "nodes": "any"}
            config.options.canary_hpc_batchspec = spec
            config.ioptions.canary_hpc_batchspec = spec
            conductor = CanaryHPCConductor(backend="shell")
            config.pluginmanager.register(conductor, f"canary_hpc{conductor.backend.name}")
            s = session.Session("tests", mode="w", force=True)
            s.add_search_paths([str(examples / "basic"), str(examples / "vvt")])
            s.discover()
            s.lock()
            s.run()
            files = glob.glob("tests/.canary/canary_hpc/batches/**/canary-inp.sh", recursive=True)
            assert len(files) == 2
