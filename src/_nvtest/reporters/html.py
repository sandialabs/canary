import os
from typing import TextIO

from _nvtest import config
from _nvtest.session import Session
from _nvtest.test.case import TestCase
from _nvtest.util import logging
from _nvtest.util.filesystem import force_remove
from _nvtest.util.filesystem import mkdirp

from .base import Reporter


def setup_parser(parser):
    sp = parser.add_subparsers(dest="child_command", metavar="")
    sp.add_parser("create", help="Create local HTML report files")


def create_report(args):
    with logging.level(logging.WARNING):
        session = Session(os.getcwd(), mode="r")
    reporter = HTMLReporter(session)
    if args.child_command == "create":
        reporter.create()
    else:
        raise ValueError(f"{args.child_command}: unknown `nvtest report html` subcommand")


class HTMLReporter(Reporter):
    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.html_dir = os.path.join(session.root, "_reports/html")
        self.cases_dir = os.path.join(self.html_dir, "cases")
        self.index = os.path.join(session.root, "Results.html")

    def create(self):
        """Collect information and create reports"""
        force_remove(self.html_dir)
        mkdirp(self.cases_dir)
        for case in self.data.cases:
            file = os.path.join(self.cases_dir, f"{case.id}.html")
            with open(file, "w") as fh:
                self.generate_case_file(case, fh)
        with open(self.index, "w") as fh:
            self.generate_index(fh)
        f = os.path.relpath(self.index, config.get("session:invocation_dir"))
        logging.info(f"HTML report written to {f}")

    @property
    def style(self) -> str:
        ts = "<style>\n"
        ts += "table{font-family:arial,sans-serif;border-collapse:collapse;}\n"
        ts += "td, th {border: 1px solid #dddddd; text-align: left; "
        ts += "padding: 8px; width: 100%}\n"
        ts += "tr:nth-child(even) {background-color: #dddddd;}\n"
        ts += "</style>"
        return ts

    @property
    def head(self) -> str:
        return f"<head>\n{self.style}\n</head>\n"

    def generate_case_file(self, case: TestCase, fh: TextIO) -> None:
        if case.skipped or case.mask:
            return
        fh.write("<html>\n")
        fh.write("<body>\n<table>\n")
        fh.write(f"<tr><td><b>Test:</b> {case.display_name}</td></tr>\n")
        fh.write(f"<tr><td><b>Status:</b> {case.status.name}</td></tr>\n")
        fh.write(f"<tr><td><b>Exit code:</b> {case.returncode}</td></tr>\n")
        fh.write(f"<tr><td><b>ID:</b> {case.id}</td></tr>\n")
        fh.write(f"<tr><td><b>Duration:</b> {case.duration}</td></tr>\n")
        fh.write("</table>\n")
        fh.write("<h2>Test output</h2>\n<pre>\n")
        if os.path.exists(case.logfile()):
            with open(case.logfile()) as fp:
                fh.write(fp.read())
        else:
            fh.write("Log file does not exist\n")
        fh.write("</pre>\n</body>\n</html>\n")

    def generate_index(self, fh: TextIO) -> None:
        fh.write("<html>\n")
        fh.write(self.head)
        fh.write("<body>\n<h1>NVTest Summary</h1>\n")
        fh.write("<table>\n<tr>")
        for col in (
            "Site",
            "Project",
            "Not Run",
            "Timeout",
            "Fail",
            "Diff",
            "Pass",
            "Total",
        ):
            fh.write(f"<th>{col}</th>")
        fh.write("</tr>\n")
        totals: dict[str, list[TestCase]] = {}
        for case in self.data.cases:
            if case.mask:
                continue
            if case.skipped:
                group = "Not Run"
            else:
                group = case.status.name.title()
            totals.setdefault(group, []).append(case)
        fh.write("<tr>")
        fh.write(f"<td>{config.get('system:host')}</td>")
        fh.write(f"<td>{config.get('build:project')}</td>")
        for group in ("Not Run", "Timeout", "Fail", "Diff", "Pass"):
            if group not in totals:
                fh.write("<td>0</td>")
            else:
                n = len(totals[group])
                file = os.path.join(self.html_dir, "%s.html" % "".join(group.split()))
                fh.write(f'<td><a href="file://{file}">{n}</a></td>')
                with open(file, "w") as fp:
                    self.generate_group_index(totals[group], fp)
        file = os.path.join(self.html_dir, "Total.html")
        fh.write(f'<td><a href="file://{file}">{len(self.data.cases)}</a></td>')
        with open(file, "w") as fp:
            self.generate_all_tests_index(totals, fp)
        fh.write("</tr>\n")
        fh.write("</table>\n</body>\n</html>")

    def generate_group_index(self, cases, fh: TextIO) -> None:
        assert all([cases[0].status.name == c.status.name for c in cases[1:]])
        fh.write("<html>\n")
        fh.write(self.head)
        fh.write(f"<body>\n<h1> {cases[0].status.name} Summary </h1>\n")
        fh.write('<table class="sortable">\n')
        fh.write("<thead><tr><th>Test</th><th>Duration</th><th>Status</th></tr></thead>\n")
        fh.write("<tbody>")
        for case in sorted(cases, key=lambda c: c.duration):
            file = os.path.join(self.cases_dir, f"{case.id}.html")
            if not os.path.exists(file):
                raise ValueError(f"{file}: html file not found")
            link = f'<a href="file://{file}">{case.display_name}</a>'
            fh.write(
                f"<tr><td>{link}</td><td>{case.duration:.2f}</td>"
                f"<td>{case.status.html_name}</td></tr>\n"
            )
        fh.write("</tbody>")
        fh.write("</table>\n</body>\n</html>")

    def generate_all_tests_index(self, totals: dict, fh: TextIO) -> None:
        fh.write("<html>\n")
        fh.write(self.head)
        fh.write("<body>\n<h1>Test Results</h1>\n<table>\n")
        fh.write("<tr><th>Test</th><th>Duration</th><th>Status</th></tr>\n")
        for group, cases in totals.items():
            for case in sorted(cases, key=lambda c: c.duration):
                file = os.path.join(self.cases_dir, f"{case.id}.html")
                if not os.path.exists(file):
                    raise ValueError(f"{file}: html file not found")
                link = f'<a href="file://{file}">{case.display_name}</a>'
                fh.write(
                    f"<tr><td>{link}</td><td>{case.duration:.2f}</td>"
                    f"<td>{case.status.html_name}</td></tr>\n"
                )
        fh.write("</table>\n</body>\n</html>")
