import bisect
import inspect
from functools import wraps

nvtest_commands: list[object] = []


def _defines_method(cls, method_name):
    method = getattr(cls, method_name, None)
    return callable(method)


def _add_command(cmdclass, family):
    order = {"info": 0, "batching": 1, "testing": 2}.get(family, 10)
    cmdclass._order_ = order
    bisect.insort(nvtest_commands, cmdclass, key=lambda x: (x._order_, x.name))


def command(*args, **kwargs):
    def _command(cmdclass: object):
        if not inspect.isclass(cmdclass):
            raise TypeError("nvtest.plugins.command must wrap classes")

        for method in ("add_options", "setup", "run", "teardown"):
            if not _defines_method(cmdclass, method):
                raise AttributeError(
                    f"{cmdclass.__name__} must define a {method} method"
                )

        for attr in ("description",):
            if not hasattr(cmdclass, attr):
                raise AttributeError(
                    f"{cmdclass.__name__} must define a {attr} attribute"
                )

        if not hasattr(cmdclass, "name"):
            cmdclass.name = cmdclass.__name__.lower()
        _add_command(cmdclass, family)

        @wraps(cmdclass, updated=())
        class _wrapped(cmdclass):  # type: ignore
            ...

        return _wrapped

    if len(args) > 1:
        n = len(args)
        raise TypeError(f"command() takes 1 positional argument but {n} were given")
    elif args and kwargs:
        family = kwargs.pop("family", None)
        if kwargs:
            kwd = next(iter(kwargs))
            raise TypeError(f"command() got an unexpected keyword argument {kwd!r}")
        return _command(args[0])
    elif kwargs:
        family = kwargs.pop("family", None)
        if kwargs:
            kwd = next(iter(kwargs))
            raise TypeError(f"command() got an unexpected keyword argument {kwd!r}")
        return _command
    elif args:
        family = None
        return _command(args[0])
    else:
        family = None
        return _command


def get_command(cmdname):
    for cmdclass in nvtest_commands:
        if cmdname == cmdclass.name:
            return cmdclass
