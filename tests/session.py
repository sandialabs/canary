import os
import types

import hpc_connect

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
            config.options.batch = {"scheduler": "none", "count": 2, "scheme": "count"}
            config.scheduler = hpc_connect.scheduler("none")
            s = session.Session("tests", mode="w", force=True)
            s.add_search_paths([os.path.join(p.examples, "basic"), os.path.join(p.examples, "vvt")])
            s.discover()
            s.lock()
            s.run()
            d1 = os.listdir("tests/.canary/batches")[0]
            d2 = os.listdir(os.path.join("tests/.canary/batches", d1))[0]
            id = d1 + d2
            f1 = s.batch_logfile(id)
            with working_dir("tests"):
                s = session.Session.batch_view(".", id)


def test_session_fail_fast(tmpdir):
    p = paths()
    with working_dir(tmpdir.strpath, create=True):
        s = session.Session("tests", mode="w", force=True)
        s.add_search_paths(os.path.join(p.examples, "status"))
        s.discover()
        s.lock()
        rc = s.run(fail_fast=True)
        assert rc != 0
