import argparse
from typing import Optional

import _nvtest.plugin as plugin
from _nvtest import config
from _nvtest import enums
from _nvtest._version import __version__
from _nvtest._version import version
from _nvtest._version import version_tuple
from _nvtest.abc import AbstractTestGenerator
from _nvtest.command import Command
from _nvtest.config.argparsing import Parser
from _nvtest.error import TestDiffed
from _nvtest.error import TestFailed
from _nvtest.error import TestSkipped
from _nvtest.main import console_main
from _nvtest.reporter import Reporter
from _nvtest.session import Session
from _nvtest.test.case import TestCase
from _nvtest.test.instance import TestInstance
from _nvtest.util import filesystem
from _nvtest.util import logging
from _nvtest.util import module
from _nvtest.util import shell
from _nvtest.util.executable import Executable

from . import directives
from . import patterns


def make_std_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", action="store_true")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--analyze", action="store_true")
    group.add_argument("--execute-analysis-sections", action="store_true")
    return parser


def get_instance() -> Optional[TestInstance]:
    try:
        return TestInstance.load()
    except FileNotFoundError:
        return None


def __getattr__(name):
    import _nvtest

    if name == "FILE_SCANNING":
        return _nvtest.FILE_SCANNING
    elif name == "test":
        test = type("Test", (), {"instance": get_instance()})()
        return test
    raise AttributeError(name)
