import _nvtest.plugin as plugin
from _nvtest.config import Config
from _nvtest.config.argparsing import Parser
from _nvtest.directives import enums
from _nvtest.error import TestDiffed
from _nvtest.error import TestFailed
from _nvtest.error import TestSkipped
from _nvtest.main import console_main
from _nvtest.session import Session
from _nvtest.test.enums import Result
from _nvtest.test.testcase import TestCase
from _nvtest.util import filesystem
from _nvtest.util import tty
from _nvtest.util.executable import Executable
from _nvtest.util.filesystem import which

version_info = (0, 0, 1)
version = ".".join(str(_) for _ in version_info)


def __getattr__(name):
    import inspect

    import _nvtest
    from _nvtest.directives.directive import Directive
    from _nvtest.directives.directive import DummyDirective
    from _nvtest.test.testinstance import TestInstance

    if name == "directives":
        for frame_info in inspect.stack():
            if "__testfile__" in frame_info.frame.f_globals:
                testfile = frame_info.frame.f_globals["__testfile__"]
                return Directive(testfile)
        return DummyDirective()
    elif name == "FILE_SCANNING":
        return _nvtest.FILE_SCANNING
    elif name == "test":
        test = type("", (), {})()
        test.instance = TestInstance.load()
        return test

    raise AttributeError(name)
