# mypy: allow-untyped-defs
"""Monkeypatching and mocking functionality."""

import os
import re
import sys
import warnings
from contextlib import contextmanager
from typing import Any
from typing import Generator
from typing import List
from typing import Mapping
from typing import MutableMapping
from typing import Optional
from typing import Tuple
from typing import TypeVar
from typing import Union
from typing import final
from typing import overload

RE_IMPORT_ERROR_NAME = re.compile(r"^No module named (.*)$")


K = TypeVar("K")
V = TypeVar("V")


def resolve(name: str) -> object:
    # Simplified from zope.dottedname.
    parts = name.split(".")

    used = parts.pop(0)
    found: object = __import__(used)
    for part in parts:
        used += "." + part
        try:
            found = getattr(found, part)
        except AttributeError:
            pass
        else:
            continue
        # We use explicit un-nesting of the handling block in order
        # to avoid nested exceptions.
        try:
            __import__(used)
        except ImportError as ex:
            expected = str(ex).split()[-1]
            if expected == used:
                raise
            else:
                raise ImportError(f"import error in {used}: {ex}") from ex
        found = annotated_getattr(found, part, used)
    return found


def annotated_getattr(obj: object, name: str, ann: str) -> object:
    try:
        obj = getattr(obj, name)
    except AttributeError as e:
        raise AttributeError(
            f"{type(obj).__name__!r} object at {ann} has no attribute {name!r}"
        ) from e
    return obj


def derive_importpath(import_path: str, raising: bool) -> Tuple[str, object]:
    if not isinstance(import_path, str) or "." not in import_path:
        raise TypeError(f"must be absolute import path string, not {import_path!r}")
    module, attr = import_path.rsplit(".", 1)
    target = resolve(module)
    if raising:
        annotated_getattr(target, attr, ann=module)
    return attr, target


class Notset:
    def __repr__(self) -> str:
        return "<notset>"


notset = Notset()


@final
class monkeypatch:
    """Helper to conveniently monkeypatch attributes/items/environment
    variables/syspath.

    Returned by the :fixture:`monkeypatch` fixture.

    .. versionchanged:: 6.2
        Can now also be used directly as `monkeypatch()`, for when
        the fixture is not available. In this case, use
        :meth:`with monkeypatch.context() as mp: <context>` or remember to call
        :meth:`undo` explicitly.
    """

    def __init__(self) -> None:
        self._setattr: List[Tuple[object, str, object]] = []
        self._setitem: List[Tuple[Mapping[Any, Any], object, object]] = []
        self._cwd: Optional[str] = None
        self._savesyspath: Optional[List[str]] = None

    @classmethod
    @contextmanager
    def context(cls) -> Generator["monkeypatch", None, None]:
        """Context manager that returns a new :class:`monkeypatch` object
        which undoes any patching done inside the ``with`` block upon exit.

        Example:
        .. code-block:: python

            import functools


            def test_partial(monkeypatch):
                with monkeypatch.context() as m:
                    m.setattr(functools, "partial", 3)

        Useful in situations where it is desired to undo some patches before the test ends,
        such as mocking ``stdlib`` functions that might break pytest itself if mocked (for examples
        of this see :issue:`3290`).
        """
        m = cls()
        try:
            yield m
        finally:
            m.undo()

    @overload
    def setattr(
        self,
        target: str,
        name: object,
        value: Notset = ...,
        raising: bool = ...,
    ) -> None: ...

    @overload
    def setattr(
        self,
        target: object,
        name: str,
        value: object,
        raising: bool = ...,
    ) -> None: ...

    def setattr(
        self,
        target: Union[str, object],
        name: Union[object, str],
        value: object = notset,
        raising: bool = True,
    ) -> None:
        """
        Set attribute value on target, memorizing the old value.

        For example:

        .. code-block:: python

            import os

            monkeypatch.setattr(os, "getcwd", lambda: "/")

        The code above replaces the :func:`os.getcwd` function by a ``lambda`` which
        always returns ``"/"``.

        For convenience, you can specify a string as ``target`` which
        will be interpreted as a dotted import path, with the last part
        being the attribute name:

        .. code-block:: python

            monkeypatch.setattr("os.getcwd", lambda: "/")

        Raises :class:`AttributeError` if the attribute does not exist, unless
        ``raising`` is set to False.

        **Where to patch**

        ``monkeypatch.setattr`` works by (temporarily) changing the object that a name points to with another one.
        There can be many names pointing to any individual object, so for patching to work you must ensure
        that you patch the name used by the system under test.

        See the section :ref:`Where to patch <python:where-to-patch>` in the :mod:`unittest.mock`
        docs for a complete explanation, which is meant for :func:`unittest.mock.patch` but
        applies to ``monkeypatch.setattr`` as well.
        """
        __tracebackhide__ = True
        import inspect

        if isinstance(value, Notset):
            if not isinstance(target, str):
                raise TypeError(
                    "use setattr(target, name, value) or "
                    "setattr(target, value) with target being a dotted "
                    "import string"
                )
            value = name
            name, target = derive_importpath(target, raising)
        else:
            if not isinstance(name, str):
                raise TypeError(
                    "use setattr(target, name, value) with name being a string or "
                    "setattr(target, value) with target being a dotted "
                    "import string"
                )

        oldval = getattr(target, name, notset)
        if raising and oldval is notset:
            raise AttributeError(f"{target!r} has no attribute {name!r}")

        # avoid class descriptors like staticmethod/classmethod
        if inspect.isclass(target):
            oldval = target.__dict__.get(name, notset)
        self._setattr.append((target, name, oldval))
        setattr(target, name, value)

    def delattr(
        self,
        target: Union[object, str],
        name: Union[str, Notset] = notset,
        raising: bool = True,
    ) -> None:
        """Delete attribute ``name`` from ``target``.

        If no ``name`` is specified and ``target`` is a string
        it will be interpreted as a dotted import path with the
        last part being the attribute name.

        Raises AttributeError it the attribute does not exist, unless
        ``raising`` is set to False.
        """
        __tracebackhide__ = True
        import inspect

        if isinstance(name, Notset):
            if not isinstance(target, str):
                raise TypeError(
                    "use delattr(target, name) or "
                    "delattr(target) with target being a dotted "
                    "import string"
                )
            name, target = derive_importpath(target, raising)

        if not hasattr(target, name):
            if raising:
                raise AttributeError(name)
        else:
            oldval = getattr(target, name, notset)
            # Avoid class descriptors like staticmethod/classmethod.
            if inspect.isclass(target):
                oldval = target.__dict__.get(name, notset)
            self._setattr.append((target, name, oldval))
            delattr(target, name)

    def setitem(self, dic: Mapping[K, V], name: K, value: V) -> None:
        """Set dictionary entry ``name`` to value."""
        self._setitem.append((dic, name, dic.get(name, notset)))
        # Not all Mapping types support indexing, but MutableMapping doesn't support TypedDict
        dic[name] = value  # type: ignore[index]

    def delitem(self, dic: Mapping[K, V], name: K, raising: bool = True) -> None:
        """Delete ``name`` from dict.

        Raises ``KeyError`` if it doesn't exist, unless ``raising`` is set to
        False.
        """
        if name not in dic:
            if raising:
                raise KeyError(name)
        else:
            self._setitem.append((dic, name, dic.get(name, notset)))
            # Not all Mapping types support indexing, but MutableMapping doesn't support TypedDict
            del dic[name]  # type: ignore[attr-defined]

    def setenv(self, name: str, value: str, prepend: Optional[str] = None) -> None:
        """Set environment variable ``name`` to ``value``.

        If ``prepend`` is a character, read the current environment variable
        value and prepend the ``value`` adjoined with the ``prepend``
        character.
        """
        if not isinstance(value, str):
            warnings.warn(  # type: ignore[unreachable]
                UserWarning(
                    f"Value of environment variable {name} type should be str, but got "
                    f"{value!r} (type: {type(value).__name__}); converted to str implicitly"
                ),
                stacklevel=2,
            )
            value = str(value)
        if prepend and name in os.environ:
            value = value + prepend + os.environ[name]
        self.setitem(os.environ, name, value)

    def delenv(self, name: str, raising: bool = True) -> None:
        """Delete ``name`` from the environment.

        Raises ``KeyError`` if it does not exist, unless ``raising`` is set to
        False.
        """
        environ: MutableMapping[str, str] = os.environ
        self.delitem(environ, name, raising=raising)

    def syspath_prepend(self, path) -> None:
        """Prepend ``path`` to ``sys.path`` list of import locations."""
        if self._savesyspath is None:
            self._savesyspath = sys.path[:]
        sys.path.insert(0, str(path))

        # https://github.com/pypa/setuptools/blob/d8b901bc/docs/pkg_resources.txt#L162-L171
        # this is only needed when pkg_resources was already loaded by the namespace package
        if "pkg_resources" in sys.modules:
            from pkg_resources import fixup_namespace_packages

            fixup_namespace_packages(str(path))

        # A call to syspathinsert() usually means that the caller wants to
        # import some dynamically created files, thus with python3 we
        # invalidate its import caches.
        # This is especially important when any namespace package is in use,
        # since then the mtime based FileFinder cache (that gets created in
        # this case already) gets not invalidated when writing the new files
        # quickly afterwards.
        from importlib import invalidate_caches

        invalidate_caches()

    def chdir(self, path: Union[str, "os.PathLike[str]"]) -> None:
        """Change the current working directory to the specified path.

        :param path:
            The path to change into.
        """
        if self._cwd is None:
            self._cwd = os.getcwd()
        os.chdir(path)

    def undo(self) -> None:
        """Undo previous changes.

        This call consumes the undo stack. Calling it a second time has no
        effect unless you do more monkeypatching after the undo call.

        There is generally no need to call `undo()`, since it is
        called automatically during tear-down.

        .. note::
            The same `monkeypatch` fixture is used across a
            single test function invocation. If `monkeypatch` is used both by
            the test function itself and one of the test fixtures,
            calling `undo()` will undo all of the changes made in
            both functions.

            Prefer to use :meth:`context() <monkeypatch.context>` instead.
        """
        for obj, name, value in reversed(self._setattr):
            if value is not notset:
                setattr(obj, name, value)
            else:
                delattr(obj, name)
        self._setattr[:] = []
        for dictionary, key, value in reversed(self._setitem):
            if value is notset:
                try:
                    # Not all Mapping types support indexing, but MutableMapping doesn't support TypedDict
                    del dictionary[key]  # type: ignore[attr-defined]
                except KeyError:
                    pass  # Was already deleted, so we have the desired state.
            else:
                # Not all Mapping types support indexing, but MutableMapping doesn't support TypedDict
                dictionary[key] = value  # type: ignore[index]
        self._setitem[:] = []
        if self._savesyspath is not None:
            sys.path[:] = self._savesyspath
            self._savesyspath = None

        if self._cwd is not None:
            os.chdir(self._cwd)
            self._cwd = None
