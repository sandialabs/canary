# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Fixtures for the protocol tests: a workspace with tests to run, and a server for it."""

import subprocess
import sys

import pytest

from _canary.service.fs import server
from _canary.service.fs.testing import Serving

PASSING = 'import sys\nif __name__ == "__main__":\n    sys.exit(0)\n'
FAILING = 'import sys\nif __name__ == "__main__":\n    sys.exit(1)\n'
SLOW = 'import sys, time\nif __name__ == "__main__":\n    time.sleep(60)\n    sys.exit(0)\n'


@pytest.fixture
def root(tmp_path, monkeypatch):
    """A workspace's root; its anchor holds ok/, failing/ and slow/ test directories."""
    monkeypatch.setattr(server, "TICK", 0.05)
    monkeypatch.setattr(server, "HEARTBEAT_INTERVAL", 0.2)
    monkeypatch.setattr(server, "INTERRUPT_GRACE", 5.0)
    for name, body in (("ok", PASSING), ("failing", FAILING), ("slow", SLOW)):
        (tmp_path / name).mkdir()
        (tmp_path / name / f"{name}.pyt").write_text(body)
    init = subprocess.run([sys.executable, "-m", "canary", "init", "."], cwd=tmp_path)
    assert init.returncode == 0
    return tmp_path / ".canary"


@pytest.fixture
def serving(root):
    s = Serving(root).start()
    yield s
    s.stop()
