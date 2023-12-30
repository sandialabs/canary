import os
import sys
from typing import TYPE_CHECKING

from ..test.testfile import AbstractTestFile
from ..util import graph
from .common import add_mark_arguments
from .common import add_resource_arguments
from .common import set_default_resource_args

if TYPE_CHECKING:
    import argparse

    from _nvtest.config.argparsing import Parser


description = "Print information about a test"


def setup_parser(parser: "Parser"):
    add_mark_arguments(parser)
    add_resource_arguments(parser)
    parser.add_argument("file", help="Test file")


def describe(args: "argparse.Namespace") -> int:
    set_default_resource_args(args)
    file = AbstractTestFile(args.file)
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
        avail_cpus=args.cpus_per_test,
        avail_devices=args.devices_per_test,
        on_options=args.on_options,
        keyword_expr=args.keyword_expr,
    )
    fp.write(f"{len(cases)} test cases:\n")
    graph.print(cases)
    return 0
