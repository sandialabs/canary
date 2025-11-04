# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse

import schema

import _canary.config as config
import _canary.enums as enums
from _canary.config.argparsing import Parser
from _canary.config.config import Config
from _canary.config.config import ConfigScope
from _canary.enums import centered_parameter_space
from _canary.enums import list_parameter_space
from _canary.enums import random_parameter_space
from _canary.error import TestDiffed
from _canary.error import TestFailed
from _canary.error import TestSkipped
from _canary.generator import AbstractTestGenerator
from _canary.main import console_main
from _canary.plugins.hookspec import hookimpl
from _canary.plugins.hookspec import hookspec
from _canary.plugins.manager import CanaryPluginManager
from _canary.plugins.types import CanaryReporter
from _canary.plugins.types import CanarySubcommand
from _canary.repo import Repo
from _canary.session import Session
from _canary.testcase import DependencyPatterns
from _canary.testcase import TestCase
from _canary.testcase import TestMultiCase
from _canary.testinstance import TestInstance
from _canary.testinstance import TestMultiInstance
from _canary.testinstance import load as load_instance
from _canary.third_party import color
from _canary.util import _difflib as difflib
from _canary.util import filesystem
from _canary.util import graph
from _canary.util import logging as _logging
from _canary.util import module
from _canary.util import shell
from _canary.util import string
from _canary.util import time
from _canary.util.executable import Executable
from _canary.version import version  # noqa: I001
from _canary.version import version_info  # noqa: I001

from . import directives
from . import patterns

get_logger = _logging.get_logger
logging = _logging.get_logger()


class TestParser(argparse.ArgumentParser):
    def parse_args(self, args=None, namespace=None):
        namespace, unknown_args = super().parse_known_args(args, namespace)
        namespace.extra_args = unknown_args
        return namespace


def make_argument_parser() -> TestParser:
    parser = TestParser()
    parser.add_argument("--stage", default="run")
    parser.add_argument("--baseline", action="store_true")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-a", action="store_true")
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
    import _canary

    if name == "FILE_SCANNING":
        return _canary.FILE_SCANNING
    elif name == "test":
        test = type("Test", (), {"instance": get_instance()})()
        return test
    raise AttributeError(name)
