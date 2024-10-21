from _nvtest.main import NVTestCommand
from _nvtest.util.filesystem import working_dir


def test_timeout(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("f1.pyt", "w") as fh:
            fh.write("""\
import sys
import time
import nvtest
nvtest.directives.timeout('1us')
def test():
    time.sleep(1)
if __name__ == '__main__':
    sys.exit(test())
""")
        run = NVTestCommand("run")
        rc = run("-w", ".")
        assert rc == 8
