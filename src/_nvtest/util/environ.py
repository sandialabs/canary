import os
from contextlib import contextmanager


@contextmanager
def tmp_environ(**kwds):
    save_env = {}
    for (var, val) in kwds.items():
        save_env[var] = os.environ.pop(var, None)
        os.environ[var] = val
    yield
    for (var, val) in save_env.items():
        os.environ.pop(var)
        if val is not None:
            os.environ[var] = val
