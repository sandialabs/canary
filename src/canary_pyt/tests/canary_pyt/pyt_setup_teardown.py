# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for per-.pyt-file setup/teardown via @canary_pyt.directives.setup/teardown.

Covers:
- scanning-time recording of the function name onto the spec attributes
  (__setup_fn__ / __teardown_fn__), and
- run-time dispatch (canary_runteststart / canary_runtest_finish hookimpls in
  canary_pyt/__init__.py) executing the functions in-process with the live Job,
  in the correct order relative to the test body.
"""

import canary_pyt
import canary_pyt.pyt as pyt
from _canary.util.filesystem import working_dir


def write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def lock_file(path: str = "test.pyt", *, on_options=None):
    m = pyt.PYTModel(".", path)
    calls = pyt.PYTLoader(file=m.file).parse()
    pyt.PYTAdapter(m).apply(calls)
    return pyt.PYTLockEmitter().lock(m, on_options=on_options or [])


# ---------------------------------------------------------------------------
# Directive is an identity decorator at run time
# ---------------------------------------------------------------------------


def test_setup_teardown_are_identity_decorators():
    def fn(job):
        return 42

    assert canary_pyt.directives.setup(fn) is fn
    assert canary_pyt.directives.teardown(fn) is fn


# ---------------------------------------------------------------------------
# Scanning records the function name onto the spec
# ---------------------------------------------------------------------------


def test_setup_recorded_on_spec(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary_pyt
canary_pyt.directives.name('t')

@canary_pyt.directives.setup
def my_setup(job):
    pass

def test():
    pass
""",
        )
        specs = lock_file()
        assert len(specs) == 1
        assert specs[0].attributes.get("__setup_fn__") == "my_setup"
        assert "__teardown_fn__" not in specs[0].attributes


def test_teardown_recorded_on_spec(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary_pyt
canary_pyt.directives.name('t')

@canary_pyt.directives.teardown
def my_teardown(job):
    pass

def test():
    pass
""",
        )
        specs = lock_file()
        assert specs[0].attributes.get("__teardown_fn__") == "my_teardown"
        assert "__setup_fn__" not in specs[0].attributes


def test_setup_and_teardown_recorded(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary_pyt
canary_pyt.directives.name('t')

@canary_pyt.directives.setup
def before(job):
    pass

@canary_pyt.directives.teardown
def after(job):
    pass

def test():
    pass
""",
        )
        specs = lock_file()
        assert specs[0].attributes.get("__setup_fn__") == "before"
        assert specs[0].attributes.get("__teardown_fn__") == "after"


def test_duplicate_setup_raises(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        write(
            "test.pyt",
            """
import canary_pyt
canary_pyt.directives.name('t')

@canary_pyt.directives.setup
def one(job):
    pass

@canary_pyt.directives.setup
def two(job):
    pass
""",
        )
        try:
            lock_file()
        except ValueError as e:
            assert "only one" in str(e)
        else:
            raise AssertionError("expected ValueError for duplicate setup")


# ---------------------------------------------------------------------------
# End-to-end: functions execute in-process with the Job, in order
# ---------------------------------------------------------------------------


def test_setup_teardown_run_end_to_end(tmp_path):
    import canary
    from _canary.workspace import Workspace

    root = tmp_path / "suite"
    root.mkdir()

    (root / "t.pyt").write_text(
        "import os\n"
        "import canary\n"
        "import canary_pyt\n"
        "canary_pyt.directives.name('t')\n"
        "\n"
        "@canary_pyt.directives.setup\n"
        "def my_setup(job):\n"
        "    open(os.path.join(job.spec.file_root, 'setup.marker'), 'w').close()\n"
        "\n"
        "@canary_pyt.directives.teardown\n"
        "def my_teardown(job):\n"
        "    open(os.path.join(job.spec.file_root, 'teardown.marker'), 'w').close()\n"
        "\n"
        "def test():\n"
        "    self = canary.get_instance()\n"
        "    # setup ran before us; teardown has not\n"
        "    assert os.path.exists(os.path.join(self.file_root, 'setup.marker'))\n"
        "    assert not os.path.exists(os.path.join(self.file_root, 'teardown.marker'))\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    test()\n"
    )

    with working_dir(root):
        with canary.config.override():
            workspace = Workspace.create(root)
            specs = workspace.collect({str(root): []})
            workspace.run(specs, only="all")
        jobs = workspace.load_jobs()

    assert (root / "setup.marker").exists()
    assert (root / "teardown.marker").exists()
    assert len(jobs) == 1
    assert jobs[0].status.outcome.name in ("SUCCESS", "PASS"), (
        f"{jobs[0].status.outcome.name}: {jobs[0].status.reason}"
    )
