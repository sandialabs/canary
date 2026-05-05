import _canary.util.filesystem as fs
from _canary.util.testing import CanaryCommand


def test_issue_89_vvt(tmpdir):
    demo = """
# VVT: parameterize (testname="abc_run or abc_post", autotype) : my_var = .1
#
# VVT: name : abc_run
#
# VVT: name : abc_post
# VVT: depends on (testname="abc_post") : abc_run.my_var=${my_var}
#
if __name__ == '__main__':
    print("Hello world")
"""
    with fs.working_dir(tmpdir.strpath, create=True):
        with open("demo.vvt", "w") as fh:
            fh.write(demo)
        run = CanaryCommand("run")
        cp = run(".")
        assert cp.returncode == 0


def test_issue_89_pyt(tmpdir):
    demo = """
import canary
canary.directives.parameterize('my_var', (0.1,), when={'testname': 'abc_run or abc_post'})
canary.directives.name('abc_run')
canary.directives.name('abc_post')
canary.directives.depends_on('abc_run.my_var=${my_var}', when={'testname': 'abc_post'})
#
if __name__ == '__main__':
    print("Hello world")
"""
    with fs.working_dir(tmpdir.strpath, create=True):
        with open("demo.pyt", "w") as fh:
            fh.write(demo)
        run = CanaryCommand("run")
        cp = run(".")
        assert cp.returncode == 0
