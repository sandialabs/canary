import os
import sys
from typing import TYPE_CHECKING

from _nvtest.config import Config

from ..test.testfile import AbstractTestFile
from ..util import graph
from .common import add_mark_arguments

if TYPE_CHECKING:
    import argparse

    from _nvtest.config.argparsing import Parser


description = "Print information about a test"


def setup_parser(parser: "Parser"):
    add_mark_arguments(parser)
    parser.add_argument("file", help="Test file")


def describe(config: "Config", args: "argparse.Namespace") -> int:
    file = AbstractTestFile(args.file)
    config = Config()
    config.set_main_options(args)
    fp = sys.stdout
    fp.write(f"--- {file.name} ------------\n")
    fp.write(f"File: {file.file}\n")
    fp.write(f"Keywords: {', '.join(file.keywords())}\n")
    if file._sources:
        fp.write("Source files:\n")
        grouped: dict[str, list[tuple[str, str]]] = {}
        for ns in file._sources:
            assert isinstance(ns.action, str)
            src, dst = ns.value
            grouped.setdefault(ns.action, []).append((src, dst))
        for action, files in grouped.items():
            fp.write(f"  {action.title()}:\n")
            for src, dst in files:
                fp.write(f"    {src}")
                if dst and dst != os.path.basename(src):
                    fp.write(f" -> {dst}")
                fp.write("\n")
    cases = file.freeze(
        cpu_count=config.machine.cpu_count,
        on_options=args.on_options,
        keyword_expr=args.keyword_expr,
    )
    fp.write(f"{len(cases)} test cases:\n")
    graph.print(cases)
    return 0
