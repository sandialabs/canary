from _nvtest.test.testcase import TestCase
from _nvtest.util.environ import tmp_environ
from _nvtest.util.filesystem import working_dir

from .common import Command


class RunCase(Command):
    name = "run-case"
    description = "Run an individual test case"

    def run(self) -> int:
        case = TestCase.load(self.session.option.file)
        with working_dir(case.exec_root):
            with tmp_environ(**case.rc_environ()):
                case.run()
        if getattr(self.session.option, "1", False):
            print(case.to_json())
        return case.returncode

    @staticmethod
    def add_options(parser):
        parser.add_argument("-1", action="store_true", default=False)
        parser.add_argument("file")
