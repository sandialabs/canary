import argparse

import _nvtest.plugin as plugin
from _nvtest import config
from _nvtest import diffutils
from _nvtest import directives
from _nvtest.config.argparsing import Parser
from _nvtest.directives import enums
from _nvtest.error import TestDiffed
from _nvtest.error import TestFailed
from _nvtest.error import TestSkipped
from _nvtest.main import console_main
from _nvtest.session import Session
from _nvtest.test.testcase import TestCase
from _nvtest.util import filesystem
from _nvtest.util import tty
from _nvtest.util.executable import Executable
from _nvtest.util.filesystem import which

from . import patterns

version_info = (0, 0, 1)
version = ".".join(str(_) for _ in version_info)
__version__ = version


def make_std_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--execute-analysis-sections", action="store_true")
    return parser


def __getattr__(name):
    import _nvtest
    from _nvtest.test.testinstance import TestInstance

    if name == "FILE_SCANNING":
        return _nvtest.FILE_SCANNING
    elif name == "test":
        test = type("", (), {})()
        test.instance = TestInstance.load()
        return test

    raise AttributeError(name)
