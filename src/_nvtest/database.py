import os
import pickle
from typing import Union

from .test.case import TestCase
from .third_party.lock import Lock
from .third_party.lock import ReadTransaction
from .third_party.lock import WriteTransaction
from .util.filesystem import mkdirp
from .util.graph import TopologicalSorter


class Database:
    """Manages the test session database

    Writes an index file containing information about all tests found during
    discovery (cases.data.p) and a results file for tests that are run
    (cases).  The results file is updated after the completion of each
    test case.

    Reads and writes to the results file are locked to allow running tests in parallel

    Args:
        directory: Where to store database assets
        cases: The list of test cases

    """

    def __init__(self, directory: str) -> None:
        self.directory = os.path.abspath(directory)
        lock_path = os.path.join(self.directory, "lock")
        self.lock = Lock(lock_path, default_timeout=120, desc="session.database")
        self.index_file = os.path.join(self.directory, "cases.data.p")
        self.progress_file = os.path.join(self.directory, "cases.prog.p")

    def _single_case_entry(self, case: TestCase) -> dict:
        entry = {
            "start": case.start,
            "finish": case.finish,
            "status": case.status,
            "returncode": case.returncode,
            "dependencies": case.dependencies,
        }
        return entry

    def update(self, cases: Union[TestCase, list[TestCase]]) -> None:
        """Add test case results to the database

        Args:
            cases: list of test cases to add to the database

        """
        if not isinstance(cases, list):
            cases = [cases]
        mkdirp(os.path.dirname(self.progress_file))
        with WriteTransaction(self.lock):
            with open(self.progress_file, "ab") as fh:
                for case in cases:
                    cd = self._single_case_entry(case)
                    pickle.dump({case.id: cd}, fh)

    def load(self) -> list[TestCase]:
        """Load the test results

        Returns:
            The list of ``TestCase``s

        """
        file = os.path.join(self.directory, "cases.data.p")
        if not os.path.exists(self.index_file):
            return []
        fd: dict[str, TestCase]
        with ReadTransaction(self.lock):
            with open(self.index_file, "rb") as fh:
                fd = pickle.load(fh)
            with open(self.progress_file, "rb") as fh:
                while True:
                    try:
                        cd = pickle.load(fh)
                    except EOFError:
                        break
                    else:
                        for case_id, value in cd.items():
                            fd[case_id].update(value)
        ts: TopologicalSorter = TopologicalSorter()
        for case in fd.values():
            ts.add(case, *case.dependencies)
        cases: dict[str, TestCase] = {}
        for case in ts.static_order():
            if case.exec_root is None:
                case.exec_root = os.path.dirname(self.directory)
            case.dependencies = [cases[dep.id] for dep in case.dependencies]
            cases[case.id] = case
        return list(cases.values())

    def read(self) -> dict[str, dict]:
        """Read the results file and return a dictionary of the stored ``TestCase`` attributions"""
        with ReadTransaction(self.lock):
            fd: dict[str, dict] = {}
            with open(os.path.join(self.directory, "cases"), "rb") as fh:
                while True:
                    try:
                        cd = pickle.load(fh)
                    except EOFError:
                        break
                    else:
                        for case_id, value in cd.items():
                            fd.setdefault(case_id, {}).update(value)
        return fd

    def makeindex(self, cases: list[TestCase]) -> None:
        """Store each ``TestCase`` in ``cases`` as a dictionary in the index file"""
        indexed: dict[str, TestCase] = {}
        for case in cases:
            indexed[case.id] = case
        mkdirp(os.path.dirname(self.index_file))
        with open(self.index_file, "wb") as fh:
            pickle.dump(indexed, fh)
        with open(self.progress_file, "wb") as fh:
            for case in cases:
                if case.masked:
                    continue
                cd = self._single_case_entry(case)
                pickle.dump({case.id: cd}, fh)
