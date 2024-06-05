import multiprocessing
import os
import random
import string

import _nvtest.util.filesystem as fs
from _nvtest.database import Database


def create_db():
    db = Database(os.getcwd(), mode="w")
    with db.connection(mode="w") as conn:
        conn.execute("CREATE TABLE foo (arg1 int, arg2 text)")
        conn.execute("INSERT INTO foo VALUES (?, ?)", (1, "baz"))


def update_db(i):
    mode = "a" if not i % 2 else "r"
    db = Database(os.getcwd())
    with db.connection(mode=mode) as conn:
        if mode == "r":
            conn.execute("SELECT arg2 FROM foo")
        else:
            chars = list(string.ascii_lowercase)
            random.shuffle(chars)
            word = "".join(chars)
            conn.execute("INSERT INTO foo VALUES (?, ?)", (i, word))


def test_concurrency(tmpdir):
    fs.mkdirp(tmpdir.strpath)
    with fs.working_dir(tmpdir.strpath):
        create_db()
        pool = multiprocessing.Pool(os.cpu_count() - 1)
        pool.map(update_db, range(200))
        pool.close()
