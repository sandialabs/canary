# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

from _canary import finder
from _canary.config import Config
from _canary.util.filesystem import working_dir


def test_backward_names(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import canary\ncanary.directives.keywords('a', 'b', 'c', 'd', 'e')")
    f = finder.Finder()
    f.add(workdir)
    assert len(f.roots) == 1
    assert workdir in f.roots
    f.prepare()
    files = f.discover()
    [case] = finder.generate_test_cases(files)
    case.work_tree = tmpdir.strpath
    assert case.exec_path == case.path
    assert case.exec_root == case.work_tree


def test_legacy_config():
    cfg = Config()
    file = os.path.join(os.path.dirname(__file__), "data/legacy_config.json")
    with open(file) as fh:
        cfg.load_snapshot(fh)
    fullversion = cfg.get("system:os:fullversion")
    assert (
        fullversion
        == "Linux manzano-login11 4.18.0-553.53.1.1toss.t4.x86_64 #1 SMP Wed May 21 12:12:01 PDT 2025 x86_64 x86_64"
    )
