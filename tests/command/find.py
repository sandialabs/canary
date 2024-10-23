import os

from _nvtest.main import NVTestCommand
from _nvtest.util.filesystem import working_dir


def test_find():
    d = os.path.dirname(__file__)
    with working_dir(os.path.join(d, "../..")):
        find = NVTestCommand("find")
        find("examples")
