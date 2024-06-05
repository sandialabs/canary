import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

from .util.filesystem import force_remove
from .util.filesystem import mkdirp


class Database:
    """Manages the test session database

    Args:
        directory: Where to store database assets
        mode: File mode

    """

    def __init__(self, directory: str, mode="a") -> None:
        self.file = os.path.join(os.path.abspath(directory), "nvtest.db")
        self.lock = Lock(directory)
        mkdirp(os.path.dirname(self.file))
        if mode == "w":
            force_remove(self.file)
        connection = sqlite3.connect(self.uri(mode), uri=True)
        if mode == "w":
            cursor = connection.cursor()
            cursor.execute("CREATE TABLE meta (name text, value text)")
            today = datetime.today().strftime("%c")
            cursor.execute("INSERT INTO meta VALUES (?, ?)", ("date", today))
            connection.commit()
        connection.close()

    def uri(self, arg_mode: str) -> str:
        mode = {"r": "ro", "w": "rwc", "a": "rw"}[arg_mode]
        return f"file:{self.file}?mode={mode}"

    @contextmanager
    def connection(
        self, *, mode: str = "a", timeout: float = 5.0
    ) -> Generator[sqlite3.Cursor, None, None]:
        tries: int = 5
        delay: float = 0.01
        backoff: float = 2.0
        isolation_level = "EXCLUSIVE" if mode in "aw" else "DEFERRED"
        uri = self.uri(mode)
        with self.lock:
            while tries > 1:
                try:
                    connection = sqlite3.connect(
                        uri, isolation_level=isolation_level, uri=True, timeout=timeout
                    )
                    break
                except sqlite3.OperationalError:
                    time.sleep(delay)
                tries -= 1
                delay *= backoff
            else:
                connection = sqlite3.connect(
                    uri, isolation_level=isolation_level, uri=True, timeout=timeout
                )

            try:
                cursor = connection.cursor()
                yield cursor
            finally:
                if mode in "aw":
                    connection.commit()
                cursor.close()
                connection.close()


class Lock:
    def __init__(self, path: str, timeout: float = 5.0) -> None:
        self.lock = os.path.join(os.path.abspath(path), "lock")
        self.timeout = timeout

    def __enter__(self) -> None:
        delay = 0.0001
        backoff = 2.0
        start = time.monotonic()
        while True:
            try:
                with os.fdopen(os.open(self.lock, flags=os.O_CREAT | os.O_EXCL)) as fd:
                    os.utime(fd.fileno() if os.utime in os.supports_fd else self.lock)
                break
            except (FileExistsError, OSError):
                pass
            if time.monotonic() - start > self.timeout:
                raise LockError(f"lock acquisition timed out at {self.timeout} s.")
            time.sleep(delay)
            delay *= backoff
        return

    def __exit__(self, *args):
        try:
            os.remove(self.lock)
        except Exception:
            pass


class LockError(Exception):
    pass
