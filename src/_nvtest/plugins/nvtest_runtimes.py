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

    def load(self, filename: str) -> Optional[dict]:
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
        opts: set[str] = {_ for _ in (options or [])}
        if {"opt"} & opts:
            build_type = "release"
        elif {"debug", "dbg"} & opts:
            build_type = "debug"
        else:
            build_type = "relwithdebinfo"
        if (build := db["builds"].get(build_type)) is None:
            return None
        if (details := build["tests"].get(case.fullname)) is not None:
            return details["mean"]
        return None


_runtimes = Singleton(Runtimes)


@nvtest.plugin.register(scope="test", stage="discovery")
def runtime(
    session: Session, case: "TestCase", on_options: Optional[list[str]] = []
) -> None:
    if not case.skip and (rt := _runtimes.get(case, options=on_options)) is not None:
        case.runtime = rt
