from ..test.testcase import TestCase
from ..util.environ import tmp_environ
from ..util.filesystem import working_dir

from .base import Session


class RunCase(Session):
    """Run an individual test case"""

    def run(self) -> int:
        case = TestCase.load(self.option.file)
        with working_dir(case.exec_root):
            with tmp_environ(**case.rc_environ()):
                case.run()
        if getattr(self.option, "1", False):
            print(case.to_json())
        return case.returncode

    @staticmethod
    def setup_parser(parser):
        parser.add_argument("-1", action="store_true", default=False)
        parser.add_argument("file")
