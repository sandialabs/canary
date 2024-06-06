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
    Database(os.getcwd(), mode="w")


def read_db(i):
    db = Database(os.getcwd())
    with db.open(f"foo-{i}", mode="r") as record:
        parts = record.read().split()
        assert parts[0] == str(i)


def insert_db(i):
    db = Database(os.getcwd())
    with db.open(f"foo-{i}", mode="w") as record:
        record.write(f"{i} {random_chars()}\n")


def test_save_binary(tmpdir):
    fs.mkdirp(tmpdir.strpath)
    with fs.working_dir(tmpdir.strpath):
        db = Database(os.getcwd(), mode="w")
        db.save_binary("foo", [1, 2, 3, 4])
        assert db.load_binary("foo") == [1, 2, 3, 4]


def test_concurrency(tmpdir):
    fs.mkdirp(tmpdir.strpath)
    with fs.working_dir(tmpdir.strpath):
        create_db()
        a, b = 0, 20
        workers = os.cpu_count() - 1
        with multiprocessing.Pool(workers) as pool:
            pool.map(insert_db, range(a, b))
        with multiprocessing.Pool(workers) as pool:
            pool.map(read_db, range(a, b))
