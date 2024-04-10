import argparse

import _nvtest.plugin as plugin
from _nvtest import config
from _nvtest import directives
from _nvtest._version import __version__
from _nvtest._version import version
from _nvtest._version import version_tuple
from _nvtest.config.argparsing import Parser
from _nvtest.directives import enums
from _nvtest.error import TestDiffed
from _nvtest.error import TestFailed
from _nvtest.error import TestSkipped
from _nvtest.main import console_main
from _nvtest.session import Session
from _nvtest.test.testcase import TestCase
from _nvtest.user import patterns
from _nvtest.util import filesystem
from _nvtest.util import logging
from _nvtest.util.executable import Executable
from _nvtest.util.filesystem import which


def make_std_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", action="store_true")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--analyze", action="store_true")
    group.add_argument("--execute-analysis-sections", action="store_true")
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
