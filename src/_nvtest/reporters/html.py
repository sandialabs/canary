import os
import sys
from typing import TextIO

from .. import config
from ..session import Session
from ..test.enums import Result
from ..test.testcase import TestCase
from ..util import tty
from ..util.filesystem import force_remove
from ..util.filesystem import mkdirp


def report(session: Session) -> None:
    reporter = Reporter(session)
    reporter.create_html_reports()


class TestData:
    def __init__(self, session: Session):
        self.session = session
        self.start: float = sys.maxsize
        self.finish: float = -1
        self.status: int = 0
        self.cases: list[TestCase] = []
        cases_to_run: list[TestCase] = [c for c in session.cases if not c.skip]
        for case in cases_to_run:
            self.add_test(case)

    def __len__(self):
        return len(self.cases)

    def __iter__(self):
        for case in self.cases:
            yield case

    def update_status(self, case: TestCase) -> None:
        if case.result == Result.DIFF:
            self.status |= 2**1
        elif case.result == Result.FAIL:
            self.status |= 2**2
        elif case.result == Result.TIMEOUT:
            self.status |= 2**3
        elif case.result == Result.NOTDONE:
            self.status |= 2**4
        elif case.result == Result.NOTRUN:
            self.status |= 2**5

    def add_test(self, case: TestCase) -> None:
        if self.start > case.start:
            self.start = case.start
        if self.finish < case.finish:
            self.finish = case.finish
        self.update_status(case)
        self.cases.append(case)


class Reporter:
    def __init__(self, session: Session) -> None:
        self.data = TestData(session)
        self.session = session
        self.html_dir = os.path.join(session.work_tree, "html")
        self.cases_dir = os.path.join(self.html_dir, "cases")
        self.index = os.path.join(session.work_tree, "Results.html")

    def create_html_reports(self):
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
        tty.info(f"HTML report written to {f}")

    @property
    def style(self) -> str:
        ts = "<style>"
        ts += "table{font-family:arial,sans-serif;border-collapse:collapse;}\n\n"
        ts += "td, th {border: 1px solid #dddddd; text-align: left; padding: 8px;}\n\n"
        ts += "tr:nth-child(even) {background-color: #dddddd;}\n"
        ts += "</style>"
        return ts

    @property
    def head(self) -> str:
        return f"<head>{self.style}</head>"

    def generate_case_file(self, case: TestCase, fh: TextIO) -> None:
        fh.write("<html>")
        fh.write("<body><table>")
        fh.write(f"<tr><td><b>Test:</b> {case.display_name}</td></tr>")
        fh.write(f"<tr><td><b>Status:</b> {case.result.name}</td></tr>")
        fh.write(f"<tr><td><b>Exit code:</b> {case.returncode}</td></tr>")
        fh.write(f"<tr><td><b>Duration:</b> {case.duration}</td></tr>")
        fh.write("</table><br>")
        fh.write("<b>Test output</b><br><pre>")
        with open(case.logfile) as fp:
            fh.write(fp.read())
        fh.write("</pre></body></html>")

    def generate_index(self, fh: TextIO) -> None:
        fh.write("<html>")
        fh.write(self.head)
        fh.write("<body><h1> Test Results </h1><table>")
        fh.write("<tr><th>Test</th><th>ID</th><th>Status</th></tr><br>")
        totals: dict[str, list[TestCase]] = {}
        for case in self.data.cases:
            totals.setdefault(case.result.name, []).append(case)
        for member in Result.members:
            if member not in totals:
                continue
            for case in totals[member]:
                file = os.path.join(self.cases_dir, f"{case.id}.html")
                if not os.path.exists(file):
                    raise ValueError(f"{file}: html file not found")
                link = f'<a href="file://{file}">{case.display_name}</a>'
                st = case.result.html_name
                fh.write(f"<tr><td>{link}</td><td>{case.id}</td><td>{st}</td></tr><br>")
        fh.write("</table></body></html>")
