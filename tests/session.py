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
            p = cases[0].path

        with working_dir(f"tests/{p}"):
            s = session.Session(".", mode="r")
            cases = s.filter(start=os.getcwd())
            assert len(cases) == 1
            assert cases[0].name == "test_exec_dir.np=4.x=1.234e7"


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
            d1 = os.listdir("tests/.nvtest/batch")[0]
            d2 = os.listdir(os.path.join("tests/.nvtest/batch", d1))[0]
            id = d1 + d2
            f1 = s.batch_logfile(id)
            with working_dir("tests"):
                s = session.Session(".", mode="r")
                cases = s.bfilter(batch_id=id)


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
