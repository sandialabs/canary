import os
import sys
from typing import TYPE_CHECKING

from ..finder import Finder
from ..test.testcase import TestCase
from ..util import graph
from ..util import tty
from ..util.time import hhmmss
from ..util.tty.colify import colified
from ..util.tty.color import colorize
from .base import Session
from .common import add_mark_arguments

if TYPE_CHECKING:
    from ..config.argparsing import Parser


class Find(Session):
    """Search paths for test files"""

    family = "info"

    @property
    def mode(self) -> Session.Mode:
        return self.Mode.ANONYMOUS

    @staticmethod
    def setup_parser(parser: "Parser"):
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "-p",
            dest="paths",
            action="store_true",
            default=False,
            help="Print file paths, grouped by root",
        )
        group.add_argument(
            "-f",
            dest="files",
            action="store_true",
            default=False,
            help="Print file paths",
        )
        group.add_argument(
            "-g",
            dest="graph",
            action="store_true",
            default=False,
            help="Print DAG of test cases",
        )
        group.add_argument(
            "--keywords",
            action="store_true",
            default=False,
            help="Show available keywords",
        )
        add_mark_arguments(parser)
        parser.add_argument("search_paths", nargs="*", help="Search path[s]")

    def setup(self):
        self.print_front_matter()
        self.finder = Finder()
        search_paths = self.option.search_paths or [os.getcwd()]
        for path in search_paths:
            self.finder.add(path)
        self.finder.prepare()
        self.finder.populate()
        self.cases = self.finder.test_cases(
            cpu_count=self.config.machine.cpu_count,
            keyword_expr=self.option.keyword_expr,
            on_options=self.option.on_options,
        )

    def run(self) -> int:
        cases_to_run = [case for case in self.cases if not case.skip]
        self.print_testcase_summary()
        if self.option.keywords:
            return self._print_keywords(cases_to_run)
        elif self.option.paths:
            return self._print_paths(cases_to_run)
        elif self.option.files:
            return self._print_files(cases_to_run)
        elif self.option.graph:
            return self._print_graph(cases_to_run)
        else:
            return self._print(cases_to_run)

    def teardown(self) -> None:
        ...

    def _print_paths(self, cases_to_run: list[TestCase]):
        unique_files: dict[str, set[str]] = dict()
        for case in cases_to_run:
            unique_files.setdefault(case.file_root, set()).add(case.file_path)
        _, max_width = tty.terminal_size()
        for root, paths in unique_files.items():
            label = colorize("@m{%s}" % root)
            tty.hline(label, max_width=max_width)
            cols = colified(sorted(paths), indent=2, width=max_width)
            tty.emit(cols + "\n")
        return

    def _print_files(self, cases_to_run: list[TestCase]):
        unique_files: set[str] = set()
        for case in cases_to_run:
            unique_files.add(case.file)
        for file in sorted(unique_files):
            tty.emit(file + "\n")
        return

    def _print_keywords(self, cases_to_run: list[TestCase]):
        unique_kwds: dict[str, set[str]] = dict()
        for case in cases_to_run:
            unique_kwds.setdefault(case.file_root, set()).update(case.keywords)
        _, max_width = tty.terminal_size()
        for root, kwds in unique_kwds.items():
            label = colorize("@m{%s}" % root)
            tty.hline(label, max_width=max_width)
            cols = colified(sorted(kwds), indent=2, width=max_width)
            tty.emit(cols + "\n")
        return 0

    def _print_graph(self, cases_to_run: list[TestCase]):
        graph.print(cases_to_run, file=sys.stdout)
        return 0

    def _print(self, cases_to_run: list[TestCase]):
        _, max_width = tty.terminal_size()
        tree: dict[str, list[str]] = {}
        for case in cases_to_run:
            line = f"{hhmmss(case.runtime)}    {case.name}"
            tree.setdefault(case.file_root, []).append(line)
        for root, lines in tree.items():
            cols = colified(lines, indent=2, width=max_width)
            label = colorize("@m{%s}" % root)
            tty.hline(label, max_width=max_width)
            tty.emit(cols + "\n")
            summary = f"found {len(lines)} test cases\n"
            tty.emit(summary)
        return 0
