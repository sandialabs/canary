import glob
import os

from _nvtest.main import NVTestCommand
from _nvtest.util.filesystem import working_dir


def test_batched(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        for i in range(12):
            with open(f"test_{i}.pyt", "w") as fh:
                fh.write(
                    """\
import sys
def test():
    pass
if __name__ == '__main__':
    sys.exit(test())
"""
                )

        run = NVTestCommand("run")
        rc = run("-w", "-l", "batch:count=4", "-l", "batch:scheduler=none", ".")
        dirs = os.listdir("TestResults")
        expected = [".nvtest"] + [f"test_{i}" for i in range(12)]
        assert sorted(expected) == sorted(dirs)
        batch_assets = sorted(os.listdir("TestResults/.nvtest/batch"))
        assert len(batch_assets) == 4
        files = glob.glob("TestResults/.nvtest/batch/**/nvtest-inp.sh", recursive=True)
        assert len(files) == 4
        files = glob.glob("TestResults/.nvtest/batch/**/nvtest-out.txt", recursive=True)
        assert len(files) == 4
        assert rc == 0
