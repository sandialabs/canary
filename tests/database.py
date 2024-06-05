import multiprocessing
import os
import random
import string

import _nvtest.util.filesystem as fs
from _nvtest.database import Database


def random_chars():
    chars = list(string.ascii_lowercase)
    random.shuffle(chars)
    return "".join(chars)


def create_db():
    db = Database(os.getcwd(), mode="w")
    with db.connection(mode="w") as conn:
        conn.execute("CREATE TABLE foo (arg1 int, arg2 text)")


def insert_db(i):
    mode = "a" if not i % 2 else "r"
    db = Database(os.getcwd())
    with db.connection(mode=mode) as conn:
        if mode == "r":
            conn.execute("SELECT arg2 FROM foo")
        else:
            conn.execute("INSERT INTO foo VALUES (?, ?)", (i, random_chars()))


def update_db (i):
    db = Database(os.getcwd())
    with db.connection(mode="a") as conn:
        if i % 2:
            conn.execute("INSERT INTO foo VALUES (?, ?)", (i, random_chars()))
        else:
            conn.execute("UPDATE foo SET arg2 = ? WHERE arg1 = ?", (random_chars(), i))


def read_db(i):
    db = Database(os.getcwd())
    with db.connection(mode="r") as conn:
        conn.execute("SELECT arg2 FROM foo WHERE arg1 = ?", (i,))
        word = conn.fetchone()[0]
        assert len(word) == 26, f"len({word}) = {len(word)}"


def test_concurrency(tmpdir):
    fs.mkdirp(tmpdir.strpath)
    with fs.working_dir(tmpdir.strpath):
        create_db()
        a, b = 0, 20
        workers = os.cpu_count() - 1
        with multiprocessing.Pool(workers) as pool:
            pool.map(insert_db, range(a, b))
        with multiprocessing.Pool(workers) as pool:
            pool.map(update_db, range(a, b))
        with multiprocessing.Pool(workers) as pool:
            pool.map(read_db, range(a, b))
