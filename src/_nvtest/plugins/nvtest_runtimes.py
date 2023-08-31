import json
import os
from typing import TYPE_CHECKING
from typing import Optional
from typing import Union

import nvtest
from _nvtest.session import Session
from _nvtest.util import tty
from _nvtest.util.singleton import Singleton

if TYPE_CHECKING:
    from _nvtest.test import TestCase


class Runtimes:
    root = "timing"

    def __init__(self):
        self.cache = {}

    @property
    def filename(self):
        return f"{self.root}.json"

    def load_db_for_case(self, case: "TestCase") -> Union[None, dict]:
        dirname = os.path.join(case.file_root, case.file_path)
        while True:
            if dirname in self.cache:
                return self.cache[dirname]
            f = os.path.join(dirname, self.filename)
            if os.path.exists(f):
                data = self.load(f)
                if data:
                    self.cache[dirname] = data
                    return data
            if dirname == case.file_root:
                break
            dirname = os.path.dirname(dirname)
        return None

    def load(self, filename: str) -> Union[dict, None]:
        with open(filename) as fh:
            data = json.load(fh)
            if self.root not in data:
                tty.error(f"missing field {self.root!r} in {filename}")
                return None
        return data[self.root]

    def get(
        self, case: "TestCase", options: Optional[list[str]] = []
    ) -> Union[int, float, None]:
        """Finds a specific test in the db"""
        db = self.load_db_for_case(case)
        if db is None:
            return None
        if options and "opt" in options:
            build_type = "release"
        elif options and "dbg" in options:
            build_type = "debug"
        else:
            build_type = "relwithdebinfo"
        build = db["builds"].get(build_type)
        if build is None:
            return None
        details = build["tests"].get(case.fullname)
        return None if details is None else details["mean"]


_runtimes = Singleton(Runtimes)


@nvtest.plugin.register("runtime", scope="test", stage="setup")
def runtime(
    session: Session, case: "TestCase", on_options: Optional[list[str]] = []
) -> None:
    if case.skip:
        return None
    rt = _runtimes.get(case, options=on_options)
    if rt is None:
        return None
    case.runtime = rt
