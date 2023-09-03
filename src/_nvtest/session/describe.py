import os
import sys

from ..test.testfile import AbstractTestFile
from ..util import graph
from .argparsing import ArgumentParser
from .base import Session
from .common import add_mark_arguments


class Describe(Session):
    """Print information about a test"""

    family = "info"

    @property
    def mode(self):
        return self.Mode.ANONYMOUS

    @staticmethod
    def setup_parser(parser: ArgumentParser):
        add_mark_arguments(parser)
        parser.add_argument("file", help="Test file")

    def run(self) -> int:
        file = AbstractTestFile(self.option.file)
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
            self.config,
            on_options=self.option.on_options,
            keyword_expr=self.option.keyword_expr,
        )
        fp.write(f"{len(cases)} test cases:\n")
        graph.print(cases)
        return 0
