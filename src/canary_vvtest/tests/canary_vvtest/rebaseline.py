# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""End-to-end tests for ``canary rebaseline`` of VVT tests.

Covers all three VVT baseline mechanisms:

* copy   -- ``#VVT: baseline : src, dst`` copies a produced file over the gold
  file in the source tree;
* flag   -- ``#VVT: baseline : --flag`` re-invokes the test script with the flag
  (the script must find its generated ``vvtest_util`` helper); and
* is_baseline -- the same flag form, but the script branches on
  ``vvtest_util.is_baseline`` instead of parsing ``sys.argv``.
"""

from pathlib import Path

import pytest

import _canary.config
from _canary.workspace import Workspace


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.delenv("CANARYCFG64", raising=False)
    monkeypatch.setenv("CANARY_DISABLE_KB", "1")
    monkeypatch.chdir(tmp_path)
    with _canary.config.override():
        _canary.config.pluginmanager.ensure_loaded("canary_vvtest")
        yield


def _run_and_rebaseline(tmp_path: Path, filename: str, body: str) -> None:
    (tmp_path / filename).write_text(body)

    workspace = Workspace.create(tmp_path)
    specs = workspace.collect({str(tmp_path): [filename]})
    session = workspace.run(specs, only="all")
    assert session.returncode == 0
    assert all(job.status.is_success() for job in session.jobs)

    # do_baseline consults config for the active command; rebaseline sets it.
    _canary.config._config.options.command = "rebaseline"
    for job in workspace.load_jobs():
        job.do_baseline()


def test_vvt_rebaseline_copy(tmp_path):
    (tmp_path / "gold.txt").write_text("OLD")
    _run_and_rebaseline(
        tmp_path,
        "mytest.vvt",
        "# VVT: baseline : actual.txt, gold.txt\n"
        "with open('actual.txt', 'w') as fh:\n"
        "    fh.write('NEW')\n",
    )
    assert (tmp_path / "gold.txt").read_text() == "NEW"


def test_vvt_rebaseline_flag_argv(tmp_path):
    (tmp_path / "gold.txt").write_text("OLD")
    _run_and_rebaseline(
        tmp_path,
        "mytest.vvt",
        "# VVT: baseline : --baseline\n"
        "import os\n"
        "import sys\n"
        "import vvtest_util as vvt\n"
        "if '--baseline' in sys.argv:\n"
        "    with open(os.path.join(vvt.SRCDIR, 'gold.txt'), 'w') as fh:\n"
        "        fh.write('NEW')\n",
    )
    assert (tmp_path / "gold.txt").read_text() == "NEW"


def test_vvt_rebaseline_is_baseline_flag(tmp_path):
    (tmp_path / "gold.txt").write_text("OLD")
    _run_and_rebaseline(
        tmp_path,
        "mytest.vvt",
        "# VVT: baseline : --baseline\n"
        "import os\n"
        "import vvtest_util as vvt\n"
        "if vvt.is_baseline:\n"
        "    with open(os.path.join(vvt.SRCDIR, 'gold.txt'), 'w') as fh:\n"
        "        fh.write('NEW')\n",
    )
    assert (tmp_path / "gold.txt").read_text() == "NEW"
