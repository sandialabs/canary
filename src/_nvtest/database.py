import os
import pickle
import re
import zipfile
from operator import attrgetter
from typing import Any
from typing import Callable

from .third_party.lock import Lock
from .third_party.lock import ReadTransaction
from .third_party.lock import WriteTransaction


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
        self.zfile = os.path.join(os.path.abspath(directory), "nvtest.db")
        lock_path = os.path.join(directory, "lock")
        self.lock = Lock(lock_path, default_timeout=120, desc="session.database")
        self._data: dict[str, Any] = {}

    def __contains__(self, field: str) -> bool:
        return self.contains(field)

    @staticmethod
    def sanitize_path(field: str) -> str:
        return re.sub(r"[^\w_.-]", "-", field)

    def put(self, field: str, value: Any, replace: bool = False) -> None:
        with WriteTransaction(self.lock):
            with ZipFile(self.zfile, "a") as zh:
                name = self.sanitize_path(field)
                if replace and name in zh.namelist():
                    zh.remove(name)
                zh.writestr(name, pickle.dumps(value))

    def get(self, field: str) -> Any:
        with ReadTransaction(self.lock):
            with ZipFile(self.zfile, "r") as zh:
                name = self.sanitize_path(field)
                if name not in zh.namelist():
                    return None
                return pickle.loads(zh.read(name))

    def pop(self, field: str) -> Any:
        with ReadTransaction(self.lock):
            with ZipFile(self.zfile, "r") as zh:
                name = self.sanitize_path(field)
                if name not in zh.namelist():
                    return None
                value = pickle.loads(zh.read(name))
        with WriteTransaction(self.lock):
            with ZipFile(self.zfile, "a") as zh:
                zh.remove(name)
        return value

    def contains(self, field: str) -> bool:
        with ZipFile(self.zfile, "r") as zh:
            name = self.sanitize_path(field)
            return name in zh.namelist()

    def apply(self, field: str, fun: Callable) -> None:
        data = self.pop(field)
        fun(data)
        self.put(field, data)


class ZipFile(zipfile.ZipFile):
    # From https://github.com/python/cpython/pull/19358/files
    def remove(self, member):
        """Remove a file from the archive. The archive must be open with mode 'a'"""

        if self.mode != "a":
            raise RuntimeError("remove() requires mode 'a'")
        if not self.fp:
            raise ValueError("Attempt to write to ZIP archive that was already closed")
        if self._writing:
            raise ValueError("Can't write to ZIP archive while an open writing handle exists.")

        # Make sure we have an info object
        if isinstance(member, zipfile.ZipInfo):
            # 'member' is already an info object
            zinfo = member
        else:
            # get the info object
            zinfo = self.getinfo(member)

        return self._remove_member(zinfo)

    def _remove_member(self, member):
        # get a sorted filelist by header offset, in case the dir order
        # doesn't match the actual entry order
        fp = self.fp
        entry_offset = 0
        filelist = sorted(self.filelist, key=attrgetter("header_offset"))
        for i in range(len(filelist)):
            info = filelist[i]
            # find the target member
            if info.header_offset < member.header_offset:
                continue

            # get the total size of the entry
            entry_size = None
            if i == len(filelist) - 1:
                entry_size = self.start_dir - info.header_offset
            else:
                entry_size = filelist[i + 1].header_offset - info.header_offset

            # found the member, set the entry offset
            if member == info:
                entry_offset = entry_size
                continue

            # Move entry
            # read the actual entry data
            fp.seek(info.header_offset)
            entry_data = fp.read(entry_size)

            # update the header
            info.header_offset -= entry_offset

            # write the entry to the new position
            fp.seek(info.header_offset)
            fp.write(entry_data)
            fp.flush()

        # update state
        self.start_dir -= entry_offset
        self.filelist.remove(member)
        del self.NameToInfo[member.filename]
        self._didModify = True

        # seek to the start of the central dir
        fp.seek(self.start_dir)
