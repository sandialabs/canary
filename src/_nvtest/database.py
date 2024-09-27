import json
import os
from contextlib import contextmanager
from datetime import datetime
from typing import IO
from typing import Any
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

    Args:
        directory: Where to store database assets
        mode: File mode

    """

    def __init__(self, directory: str, mode="a") -> None:
        self.home = os.path.join(os.path.abspath(directory), "objects")
        if mode in "ra":
            if not os.path.exists(self.home):
                raise FileNotFoundError(self.home)
        elif mode == "w":
            force_remove(self.home)
        else:
            raise ValueError(f"{mode!r}: unknown file mode")
        self.lock = Lock(self.join_path("lock"))
        if mode == "w":
            with self.open("DB.TAG", "w") as fh:
                fh.write(datetime.today().strftime("%c"))

    def exists(self, name: str) -> bool:
        return os.path.exists(self.join_path(name))

    def join_path(self, name: str) -> str:
        return os.path.join(self.home, name)

    @contextmanager
    def open(self, name: str, mode: str = "r") -> Generator[IO, None, None]:
        path = self.join_path(name)
        mkdirp(os.path.dirname(path))
        transaction_type: Type[LockTransaction]
        transaction_type = ReadTransaction if mode == "r" else WriteTransaction
        with transaction_type(self.lock):
            with open(path, mode) as fh:
                yield fh

    def load_json(self, name: str) -> Any:
        path = self.join_path(name)
        with ReadTransaction(self.lock):
            with open(path, "r") as fh:
                return json.load(fh)

    def save_json(self, name: str, obj: Any) -> None:
        path = self.join_path(name)
        mkdirp(os.path.dirname(path))
        with WriteTransaction(self.lock):
            with open(path, "w") as fh:
                json.dump(obj, fh, indent=2)
