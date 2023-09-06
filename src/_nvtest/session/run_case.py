import os
from ..test.testcase import TestCase
from ..util.environ import tmp_environ
from ..util.filesystem import working_dir
from .base import Session


class RunCase(Session):
    """Run an individual test case"""

    family = "test"

    def __init__(self, *, config):
        self.config = config
        self.option = self.config.option
        self.invocation_params = config.invocation_params

    def __post_init__(self):
        ...

    @property
    def mode(self):
        return self.Mode.APPEND

    def startup(self):
        ...

    def setup(self):
        ...

    def teardown(self):
        ...

    def run(self) -> int:
        case = TestCase.load(self.config.option.file)
        with working_dir(case.exec_root):
            with tmp_environ(**case.rc_environ()):
                case.run()
        if getattr(self.option, "1", False):
            print(case.to_json())
        if case.returncode != 0:
            lines = open(case.logfile).readlines()[-20:]
            print("".join(lines))
        return case.returncode

    @staticmethod
    def setup_parser(parser):
        parser.add_argument("-1", action="store_true", default=False)
        parser.add_argument("file")
