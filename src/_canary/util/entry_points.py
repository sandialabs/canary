# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT


def get_entry_points(*, group: str):
    """Wrapper for ``importlib.metadata.entry_points``

    Args:
        group: entry points to select

    Returns:
        EntryPoints for ``group`` or empty list if unsupported
    """

    try:
        import importlib.metadata  # type: ignore  # novermin
    except ImportError:
        return []

    try:
        return importlib.metadata.entry_points(group=group)
    except TypeError:
        # Prior to Python 3.10, entry_points accepted no parameters and always
        # returned a dictionary of entry points, keyed by group.  See
        # https://docs.python.org/3/library/importlib.metadata.html#entry-points
        return importlib.metadata.entry_points().get(group, [])  # type: ignore
