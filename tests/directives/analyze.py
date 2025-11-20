# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import glob
from pathlib import Path

from _canary.util.filesystem import working_dir
from _canary.util.testing import CanaryCommand


def test_analyze(tmpdir):
    generator = Path(__file__).parent / "../data/generators/analyze.pyt"
    with working_dir(tmpdir.strpath, create=True):
        run = CanaryCommand("run")
        cp = run("-w", str(generator))
        if cp.returncode != 0:
            for file in glob.glob("TestResults/**/canary-out.txt"):
                print(open(file).read())
        assert cp.returncode == 0


def test_analyze_alt_flag(tmpdir):
    generator = Path(__file__).parent / "../data/generators/analyze_alt_flag.pyt"
    with working_dir(tmpdir.strpath, create=True):
        run = CanaryCommand("run")
        cp = run("-w", str(generator))
        if cp.returncode != 0:
            for file in glob.glob("TestResults/**/canary-out.txt"):
                print(open(file).read())
        assert cp.returncode == 0


def test_analyze_script(tmpdir):
    generator = Path(__file__).parent / "../data/generators/analyze_script.pyt"
    with working_dir(tmpdir.strpath, create=True):
        run = CanaryCommand("run")
        cp = run(str(generator), debug=True)
        assert cp.returncode == 0
