import _canary.util.filesystem as fs
from _canary.util.testing import CanaryCommand


def test_issue_89(tmpdir):
    demo = """
# VVT: parameterize (testname="abc_run or abc_post", autotype) : my_var = .1
#
# VVT: name : abc_run
#
# VVT: name : abc_post
# VVT: depends on (testname="abc_post") : abc_run.my_var=${my_var}
#
print("Hello world")
"""
    with fs.working_dir(tmpdir.strpath, create=True):
        with open("demo.vvt", "w") as fh:
            fh.write(demo)
        run = CanaryCommand("run")
        cp = run(".")
        assert cp.returncode == 0
