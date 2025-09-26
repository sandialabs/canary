# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import glob
import importlib.resources
import os

import _canary.config as config
import _canary.session as session
from _canary.util.filesystem import working_dir


def test_session_bfilter(tmpdir):
    root = str(importlib.resources.files("canary"))
    examples = os.path.join(root, "examples")
    with working_dir(tmpdir.strpath, create=True):
        with config.override():
            config.pluginmanager.hook.canary_addhooks(pluginmanager=config.pluginmanager)
            config.options.batchopts = {
                "scheduler": "shell",
                "spec": {"count": 2, "duration": None, "layout": "flat", "nodes": "any"},
            }
            config.pluginmanager.hook.canary_configure(config=config)
            s = session.Session("tests", mode="w", force=True)
            s.add_search_paths([os.path.join(examples, "basic"), os.path.join(examples, "vvt")])
            s.discover()
            s.lock()
            s.run()
            files = glob.glob("tests/.canary/batches/**/canary-inp.sh", recursive=True)
            assert len(files) == 2
