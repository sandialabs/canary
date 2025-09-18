# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import glob
import os
import types

import _canary.config as config
import _canary.session as session
from _canary.util.filesystem import working_dir


def paths():
    this_dir = os.path.dirname(__file__)
    root = os.path.dirname(this_dir)
    p = types.SimpleNamespace(
        root=root, examples=os.path.join(root, "examples"), source=os.path.join(root, "src")
    )
    return p


def test_session_filter(tmpdir):
    p = paths()
    with working_dir(tmpdir.strpath, create=True):
        s = session.Session("tests", mode="w", force=True)
        s.add_search_paths([os.path.join(p.examples, "basic"), os.path.join(p.examples, "vvt")])
        s.discover()
        s.lock()
        s.run()

        with working_dir("tests"):
            s = session.Session(".", mode="r")
            s.filter(keyword_exprs=["first"])

        with working_dir("tests"):
            s = session.Session(".", mode="r")
            s.filter(parameter_expr="np=4")
            cases = s.get_ready()
            assert len(cases) == 1
            assert cases[0].family == "test_exec_dir"
            p = cases[0].path

        with working_dir(f"tests/{p}"):
            s = session.Session(".", mode="r")
            s.filter(start=os.getcwd())
            cases = s.get_ready()
            assert len(cases) == 1
            assert cases[0].name == "test_exec_dir.np=4.x=1.234e7"


def test_session_bfilter(tmpdir):
    p = paths()
    with working_dir(tmpdir.strpath, create=True):
        with config.override():
            config.pluginmanager.hook.canary_addhooks(pluginmanager=config.pluginmanager)
            config.options.batchopts = {
                "scheduler": "shell",
                "spec": {"count": 2, "duration": None, "layout": "flat", "nodes": "any"},
            }
            config.pluginmanager.hook.canary_configure(config=config)
            s = session.Session("tests", mode="w", force=True)
            s.add_search_paths([os.path.join(p.examples, "basic"), os.path.join(p.examples, "vvt")])
            s.discover()
            s.lock()
            s.run()
            # test batchfile

            files = glob.glob("tests/.canary/batches/**/config", recursive=True)
            assert len(files) == 2


def test_session_fail_fast(tmpdir):
    p = paths()
    with working_dir(tmpdir.strpath, create=True):
        with config.override():
            config.options.fail_fast = True
            s = session.Session("tests", mode="w", force=True)
            s.add_search_paths(os.path.join(p.examples, "status"))
            s.discover()
            s.lock()
            rc = s.run()
            assert rc != 0
