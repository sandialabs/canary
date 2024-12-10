import glob
import os

from _nvtest.main import NVTestCommand
from _nvtest.util.filesystem import working_dir


def test_batched(tmpdir):
    # add long keyword so that batches have a length to minimize when partitioning
    with working_dir(tmpdir.strpath, create=True):
        for i in range(12):
            with open(f"test_{i}.pyt", "w") as fh:
                fh.write(
                    """\
import sys
import nvtest
nvtest.directives.keywords('long')
def test():
    pass
if __name__ == '__main__':
    sys.exit(test())
"""
                )

        run = NVTestCommand("run")
        rc = run("-w", "-b", "count=4", "-b", "scheduler=none", ".")
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


def test_batched_extra_args(tmpdir):
    # add long keyword so that batches have a length to minimize when partitioning
    with working_dir(tmpdir.strpath, create=True):
        for i in range(12):
            with open(f"test_{i}.pyt", "w") as fh:
                fh.write(
                    """\
import sys
import nvtest
nvtest.directives.keywords('long')
def test():
    pass
if __name__ == '__main__':
    sys.exit(test())
"""
                )

        run = NVTestCommand("run")
        args = ["-w", "-b", "count=4", "-b", "scheduler=none"]
        args.extend(["-b", "args='-l place=scatter:excl,-q debug,-A XYZ123'"])
        args.append(".")
        rc = run(*args)
        dirs = os.listdir("TestResults")
        expected = [".nvtest"] + [f"test_{i}" for i in range(12)]
        assert sorted(expected) == sorted(dirs)
        batch_assets = sorted(os.listdir("TestResults/.nvtest/batch"))
        assert len(batch_assets) == 4
        files = glob.glob("TestResults/.nvtest/batch/**/nvtest-inp.sh", recursive=True)
        found = 0
        for line in open(files[0]):
            if line.strip() == "# BASH: -l place=scatter:excl":
                found += 1
            elif line.strip() == "# BASH: -q debug":
                found += 1
            elif line.strip() == "# BASH: -A XYZ123":
                found += 1
        assert found == 3
        assert len(files) == 4
        files = glob.glob("TestResults/.nvtest/batch/**/nvtest-out.txt", recursive=True)
        assert len(files) == 4
        assert rc == 0
