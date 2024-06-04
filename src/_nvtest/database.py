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
