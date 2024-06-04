import os
import sqlite3
from contextlib import contextmanager
from typing import Generator
from typing import Type

from .third_party.lock import Lock
from .third_party.lock import LockTransaction
from .third_party.lock import ReadTransaction
from .third_party.lock import WriteTransaction
from .util.filesystem import force_remove
from .util.filesystem import mkdirp


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

    def __init__(self, directory: str, mode="a") -> None:
        lock_path = os.path.join(directory, "lock")
        self.lock = Lock(lock_path, default_timeout=120, desc="session.database")
        self.file = os.path.join(os.path.abspath(directory), "nvtest.db")
        mkdirp(os.path.dirname(self.file))
        if mode == "w":
            force_remove(self.file)
        sqlite3.connect(self.file)

    @contextmanager
    def cursor(self, *, mode: str = "a") -> Generator:
        transaction_type: Type[LockTransaction]
        transaction_type = ReadTransaction if mode == "r" else WriteTransaction
        with transaction_type(self.lock):
            db = sqlite3.connect(self.file)
            cursor = db.cursor()
            try:
                yield cursor
            finally:
                if mode in "aw":
                    db.commit()
                db.close()
