# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
import shutil
import sys
import webbrowser
from importlib import resources
from pathlib import Path

from ..config.argparsing import Parser
from ..hookspec import hookimpl
from .base import CanarySubcommand


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Docs())


class Docs(CanarySubcommand):
    name = "docs"
    description = "open canary documentation in a web browser"

    def setup_parser(self, parser: "Parser") -> None:
        parser.set_defaults(docs_action="open")
        sp = parser.add_subparsers(dest="docs_action")
        sp.add_parser("open")
        p = sp.add_parser("build")
        p.add_argument(
            "-w", "--wipe", action="store_true", help="Remove docs cache before building"
        )
        p.add_argument("-d", "--dest", help="Build docs in this directory [default: ./build]")
        p.add_argument("what", nargs="?", help="What to build [default: html]")

    def execute(self, args: "argparse.Namespace") -> int:
        if args.docs_action == "build":
            docs = Path(str(resources.files("canary").joinpath("docs")))
            dest = Path(args.dest or "./build")
            if args.wipe:
                if dest.exists():
                    shutil.rmtree(dest)
                for p in ("api-docs", "user/commands", "user/directives", ".cache"):
                    if (docs / p).exists():
                        shutil.rmtree(docs / p)
            argv = [
                sys.executable,
                "-m",
                "sphinx",
                "-b",
                args.what,
                "--keep-going",
                "-v",
                "-d",
                str(dest / "doctrees"),
                str(docs),
                str(dest / args.what),
            ]
            os.execvp(sys.executable, argv)  # nosec B606
        elif args.docs_action == "open":
            webbrowser.open("https://canary-wm.readthedocs.io/en/production/")
        return 0
