import os
import types

import _nvtest.config as config
import _nvtest.session as session
from _nvtest.util.filesystem import working_dir


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
        cases = s.populate()
        s.run(cases)

        with working_dir("tests"):
            s = session.Session(".", mode="r")
            cases = s.filter(keyword_expr="first")

        with working_dir("tests"):
            s = session.Session(".", mode="r")
            cases = s.filter(parameter_expr="np=4")
            assert len(cases) == 1
            assert cases[0].family == "test_exec_dir"

        with working_dir("tests/first"):
            s = session.Session(".", mode="r")
            cases = s.filter(start=os.getcwd())
            assert len(cases) == 1
            assert cases[0].name == "first"


def test_session_bfilter(tmpdir):
    p = paths()
    with working_dir(tmpdir.strpath, create=True):
        with config.override():
            config.batch.scheduler = "none"
            config.batch.count = 2
            s = session.Session("tests", mode="w", force=True)
            s.add_search_paths(
                [os.path.join(p.examples, "basic"), os.path.join(p.examples, "vvt")]
            )
            s.discover()
            s.lock()
            cases = s.populate()
            s.run(cases)
            f1 = s.blogfile(1, None)
            f2 = s.blogfile(1, 1)
            assert f1 == f2

            with working_dir("tests"):
                s = session.Session(".", mode="r")
                cases = s.bfilter(lot_no=1, batch_no=1)


def test_session_fail_fast(tmpdir):
    p = paths()
    with working_dir(tmpdir.strpath, create=True):
        s = session.Session("tests", mode="w", force=True)
        s.add_search_paths(os.path.join(p.examples, "status"))
        s.discover()
        s.lock()
        cases = s.populate()
        rc = s.run(cases, fail_fast=True)
        assert rc != 0
