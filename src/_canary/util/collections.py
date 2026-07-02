import copy
from typing import Any
from typing import Iterable
from typing import TypeVar
from typing import overload

K1 = TypeVar("K1")
K2 = TypeVar("K2")
V1 = TypeVar("V1")
V2 = TypeVar("V2")
T1 = TypeVar("T1")
T2 = TypeVar("T2")
T = TypeVar("T")


class defaultlist(list):
    def __init__(self, factory, n=0):
        self.factory = factory
        for i in range(n):
            self.append(self.factory())

    def new(self):
        self.append(self.factory())
        return self[-1]


@overload
def merge(dest: dict[K1, V1], source: dict[K2, V2]) -> dict[K1 | K2, V1 | V2]: ...


@overload
def merge(dest: list[T1], source: list[T2]) -> list[T1 | T2]: ...


@overload
def merge(dest: None, source: None) -> None: ...


@overload
def merge(dest: object, source: None) -> None: ...


@overload
def merge(dest: None, source: T) -> T: ...


@overload
def merge(dest: object, source: object) -> Any: ...


def merge(dest: Any, source: Any) -> Any:
    """Merges source into dest; entries in source take precedence over dest.

    This routine may modify dest and should be assigned to dest, in
    case dest was None to begin with, e.g.:

       dest = merge(dest, source)

    In the result, elements from lists from ``source`` will appear before
    elements of lists from ``dest``. Likewise, when iterating over keys
    or items in merged ``OrderedDict`` objects, keys from ``source`` will
    appear before keys from ``dest``.

    Config file authors can optionally end any attribute in a dict
    with `::` instead of `:`, and the key will override that of the
    parent instead of merging.
    """

    def they_are(t: type) -> bool:
        return isinstance(dest, t) and isinstance(source, t)

    # If source is None, overwrite with source.
    if source is None:
        return None

    # Source list is prepended for precedence.
    if they_are(list):
        dest[:] = source + [x for x in dest if x not in source]
        return dest

    # Source dict is merged into dest.
    elif they_are(dict):
        # Save dest keys to reinsert later. This ensures that source items
        # come before dest items in OrderedDicts.
        dest_keys = [dk for dk in dest.keys() if dk not in source]

        for sk, sv in source.items():
            merge_objects = sk in dest
            old_dest_value = dest.pop(sk, None)

            if merge_objects:
                dest[sk] = merge(old_dest_value, sv)
            else:
                dest[sk] = copy.deepcopy(sv)

        # Reinsert dest keys so they are last in the result.
        for dk in dest_keys:
            dest[dk] = dest.pop(dk)

        return dest

    # If source and dest are different types, or are not both lists or dicts,
    # replace with source.
    return copy.copy(source)


def contains_any(sequence: Iterable[Any], *args: Any) -> Any:
    for arg in args:
        if arg in sequence:
            return arg
    return None
