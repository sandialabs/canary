import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Sequence

import _nvtest.config as config
import _nvtest.enums as enums
import _nvtest.plugin as plugin
from _nvtest._version import __version__
from _nvtest._version import version
from _nvtest._version import version_tuple
from _nvtest.command.base import Command
from _nvtest.config.argparsing import Parser
from _nvtest.enums import centered_parameter_space
from _nvtest.enums import list_parameter_space
from _nvtest.enums import random_parameter_space
from _nvtest.error import TestDiffed
from _nvtest.error import TestFailed
from _nvtest.error import TestSkipped
from _nvtest.generator import AbstractTestGenerator
from _nvtest.main import console_main
from _nvtest.reporter import Reporter
from _nvtest.session import Session
from _nvtest.test.case import TestCase
from _nvtest.test.instance import TestInstance
from _nvtest.test.instance import TestMultiInstance
from _nvtest.test.instance import load as load_instance
from _nvtest.util import filesystem
from _nvtest.util import logging
from _nvtest.util import module
from _nvtest.util import shell
from _nvtest.util.executable import Executable

from . import directives
from . import patterns


class TestParser(argparse.ArgumentParser):
    def parse_args(self, args=None, namespace=None):
        namespace, unknown_args = super().parse_known_args(args, namespace)
        namespace.extra_args = unknown_args
        return namespace


def make_argument_parser() -> TestParser:
    parser = TestParser()
    parser.add_argument("--stage")
    parser.add_argument("--baseline", action="store_true")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--analyze", action="store_true")
    group.add_argument("--execute-analysis-sections", action="store_true")
    return parser


make_std_parser = make_argument_parser


def get_instance(arg_path: str | None = None) -> TestInstance | None:
    try:
        return load_instance(arg_path=arg_path)
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
