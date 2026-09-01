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
from ..util import logging
from .base import CanarySubcommand

logger = logging.get_logger(__name__)


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
            "-w",
            "--wipe",
            action="store_true",
            help="Remove existing build directory and generated sources before building",
        )
        p.add_argument("--no-cache", action="store_true", help="Remove docs cache before building")
        p.add_argument("-d", "--dest", help="Build docs in this directory [default: ./build]")
        p.add_argument("what", nargs="?", help="What to build [default: html]")

    def execute(self, args: "argparse.Namespace") -> int:
        if args.docs_action == "build":
            what = args.what or "html"
            docs = Path(str(resources.files("canary").joinpath("docs")))
            dest = Path(args.dest or "./build")
            if args.wipe:
                if dest.exists():
                    logger.info(f"Removing {dest}")
                    shutil.rmtree(dest)
                for p in ("api-docs", "user/commands", "user/directives"):
                    if (docs / p).exists():
                        logger.info(f"Removing {docs / p}")
                        shutil.rmtree(docs / p)
            if args.no_cache:
                os.environ["DOCRUN_REFRESH_CACHE"] = "1"
            argv = [
                sys.executable,
                "-m",
                "sphinx",
                "-b",
                what,
                "--keep-going",
                "-v",
                "-d",
                str(dest / "doctrees"),
                str(docs),
                str(dest / what),
            ]
            os.execvp(sys.executable, argv)  # nosec B606
        elif args.docs_action == "open":
            webbrowser.open("https://canary-wm.readthedocs.io/en/production/")
        return 0
