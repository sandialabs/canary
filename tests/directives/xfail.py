from _canary.main import CanaryCommand
from _canary.util.filesystem import working_dir


def test_xfail(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("f1.pyt", "w") as fh:
            fh.write(
                """\
import sys
import canary
canary.directives.xfail()
def test():
    raise canary.TestFailed()
if __name__ == '__main__':
    sys.exit(test())
"""
            )
        run = CanaryCommand("run")
        rc = run("-w", ".")
        assert rc == 0
