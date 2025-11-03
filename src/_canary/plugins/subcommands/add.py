# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
import os
from typing import TYPE_CHECKING

from ...config.schemas import testpaths_schema
from ...repo import Repo
from ...third_party.color import colorize
from ...util import logging
from ...util.filesystem import working_dir
from ..hookspec import hookimpl
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser


logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Add())


class Add(CanarySubcommand):
    name = "add"
    description = "Add test generators to Canary session"

    def setup_parser(self, parser: "Parser"):
        parser.add_argument(
            "pathspec",
            action=pathspec,
            nargs="+",
            help="Add test generators found in pathspec to Canary session. "
            "See 'canary help --pathspec' for help on the path specification",
        )
        parser.add_argument(
            "-f",
            metavar="file",
            action=pathspec,
            dest="pathspec",
            help="Read test paths from a json or yaml file. "
            "See 'canary help --pathfile' for help on the file schema",
        )

    def execute(self, args: "argparse.Namespace") -> int:
        repo = Repo.load()
        repo.collect_testcase_generators(args.pathspec, pedantic=True)
        return 0


class pathspec(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        spec: dict[str, list[str]] = {}
        if option_string == "-f":
            spec.update(self.read_paths(values))
        else:
            for value in values:
                if os.path.isfile(value):
                    d, f = os.path.split(os.path.abspath(value))
                    spec.setdefault(d, []).append(f)
                elif os.path.isdir(value):
                    spec.setdefault(value, [])
                elif ":" in value:
                    d, _, f = value.partition(":")
                    if not os.path.exists(os.path.join(d, f)):
                        parser.error(f"{f} not found in {d}")
                    else:
                        spec.setdefault(d, []).append(f)
                elif value.startswith(("git@", "repo@")):
                    vcs, _, root = value.partition("@")
                    if not os.path.isdir(root):
                        parser.error(f"{vcs}@{root}: directory does not exist")
                else:
                    parser.error(f"{value}: file does not exit")
        setattr(namespace, self.dest, spec)

    @staticmethod
    def read_paths(file: str) -> dict[str, list[str]]:
        data: dict
        if file.endswith(".json"):
            with open(file, "r") as fh:
                data = json.load(fh)
        else:
            import yaml

            with open(file, "r") as fh:
                data = yaml.safe_load(fh)
        testpaths_schema.validate(data)
        file_dir = os.path.abspath(os.path.dirname(file) or ".")
        paths: dict[str, list[str]] = {}
        with working_dir(file_dir):
            for p in data["testpaths"]:
                if isinstance(p, str):
                    paths.setdefault(os.path.abspath(p), [])
                else:
                    paths.setdefault(os.path.abspath(p["root"]), []).extend(p["paths"])
        return paths

    @staticmethod
    def pathspec_help() -> str:
        text = """\
pathspec syntax:

  pathspec [-- ...]

  new test sessions:
    %(path)s                                   scan path recursively for test generators
    %(file)s                                   use this test generator
    %(lock)s                         run tests in this lock file
                                           (produced by %(find)s)
    %(git)s@path                               find tests under git version control at path
    %(repo)s@path                              find tests under repo version control at path

  inside existing test sessions:
    %(relpath)s                                   rerun test cases in this directory and its children
    %(relfile)s                                   rerun the test case defined in this file
    %(hash)s                                  rerun this test case

  examples:
    canary run path            scan path for tests to run
    canary run .               rerun tests in . (and its children)
    canary run /7yral9i        rerun test case with hash 7yral9i

  script arguments:
    Any argument following the %(sep)s separator is passed directly to each test script's command line.
""" % {
            "file": bold("file"),
            "path": bold("path"),
            "git": bold("git"),
            "repo": bold("repo"),
            "lock": bold("testcases.lock"),
            "find": bold("canary find --lock ..."),
            "relpath": bold("path"),
            "relfile": bold("file"),
            "hash": bold("/hash"),
            "sep": bold("--"),
        }
        return text

    @staticmethod
    def pathfile_help() -> str:
        text = """\
pathspec file schema syntax:

  {
    "testpaths": [
      {
        "root": str,
        "paths": [str]
      }
    ]
  }"""
        return text


def bold(arg: str) -> str:
    if os.getenv("COLOR_WHEN", "auto") == "never":
        return f"**{arg}**"
    return colorize("@*{%s}" % arg)


def code(arg: str) -> str:
    if os.getenv("COLOR_WHEN", "auto") == "never":
        return f"``{arg}``"
    return colorize("@*{%s}" % arg)
