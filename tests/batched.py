import os

from _nvtest.main import NVTestCommand
from _nvtest.util.filesystem import working_dir


def test_batched(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        for i in range(12):
            with open(f"test_{i}.pyt", "w") as fh:
                fh.write("""\
import sys
def test():
    pass
if __name__ == '__main__':
    sys.exit(test())
""")

        run = NVTestCommand("run")
        rc = run("-w", "-l", "batch:count=4", "-l", "batch:runner=shell", ".")
        dirs = [".nvtest"] + [f"test_{i}" for i in range(12)]
        assert sorted(os.listdir("TestResults")) == sorted(dirs)
        assert os.path.exists("TestResults/.nvtest/batches/1")
        batch_assets = sorted(os.listdir("TestResults/.nvtest/batches/1"))
        expected_batch_assets = [
            "batch.1-inp.sh",
            "batch.1-out.txt",
            "batch.2-inp.sh",
            "batch.2-out.txt",
            "batch.3-inp.sh",
            "batch.3-out.txt",
            "batch.4-inp.sh",
            "batch.4-out.txt",
        ]
        print(open("TestResults/.nvtest/batches/1/batch.1-out.txt").read())
        assert sorted(batch_assets) == sorted(expected_batch_assets)
        assert rc == 0
