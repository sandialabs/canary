# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import io
from typing import TYPE_CHECKING

from ...third_party.colify import colified
from ...third_party.color import colorize
from ...util import logging
from ...util.term import terminal_size
from ..hookspec import hookimpl
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Info())


class Info(CanarySubcommand):
    name = "info"
    description = "Print information about tests in a folder"

    def setup_parser(self, parser: "Parser"):
        parser.add_argument("-f", action="store_true", default=False, help="Show generator paths")
        parser.add_argument("paths", nargs="*")

    def execute(self, args: argparse.Namespace) -> int:
        import _canary.finder as finder

        f = finder.Finder()
        paths = args.paths or ["."]
        for path in paths:
            f.add(path)
        f.prepare()
        files = f.discover()

        info: dict[str, dict[str, set[str]]] = {}
        for file in files:
            myinfo = info.setdefault(file.root, {})
            finfo = file.info()
            myinfo.setdefault("keywords", set()).update(finfo.get("keywords", []))
            myinfo.setdefault("options", set()).update(finfo.get("options", []))
            type = finfo.get("type", "AbstractTestGenerator").replace("TestGenerator", "")
            myinfo.setdefault("types", set()).add(type)
            myinfo.setdefault("files", set()).add(file.path)
        _, max_width = terminal_size()
        for root, myinfo in info.items():
            fp = io.StringIO()
            label = colorize("@m{%s}" % root)
            logging.hline(label, max_width=max_width, file=fp)
            fp.write(f"Test generators: {len(files)}\n")
            fp.write(f"Test types: {'  '.join(myinfo['types'])}\n")
            if keywords := myinfo.get("keywords"):
                fp.write("Keywords:\n")
                cols = colified(sorted(keywords), indent=2, width=max_width, padding=5)
                fp.write(cols.rstrip() + "\n")
            if options := myinfo.get("options"):
                fp.write("Option expressions:\n")
                cols = colified(sorted(options), indent=2, width=max_width, padding=5)
                fp.write(cols.rstrip() + "\n")
            if args.f:
                if paths := myinfo.get("files"):
                    fp.write("Generators:\n")
                    cols = colified(sorted(paths), indent=2, width=max_width, padding=5)
                    fp.write(cols.rstrip() + "\n")
            print(fp.getvalue())
        return 0
