# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import datetime
import errno
import getpass
import grp
import os
import pathlib
import re
import shlex
import shutil
import stat
import tempfile
import time
from contextlib import contextmanager
from typing import Any
from typing import Callable
from typing import Generator

from . import logging

__all__ = [
    "ancestor",
    "grep",
    "which",
    "copyfile",
    "movefile",
    "remove",
    "rmtree2",
    "synctree",
    "getuser",
    "gethome",
    "gettempdir",
    "tmpdir",
    "gethost",
    "getnode",
    "filesize",
    "force_copy",
    "force_remove",
    "max_name_length",
    "which",
    "touch",
    "touchp",
    "working_dir",
    "mkdirp",
    "set_executable",
    "is_exe",
    "force_symlink",
    "accessible",
    "samepath",
    "find_work_tree",
]


def is_hidden(path: str) -> bool:
    return os.path.basename(path).startswith(".")


def max_name_length() -> int:
    if os.name == "nt":
        return 260
    return os.pathconf("/", "PC_NAME_MAX")


def which(
    *args: str,
    path: str | list[str] | tuple[str, ...] | None = None,
    required: bool = False,
) -> str | None:
    """Finds an executable in the path like command-line which.

    If given multiple executables, returns the first one that is found.
    If no executables are found, returns None.

    Args:
      args: One or more executables to search for
      path: The path to search. Defaults to ``PATH`` required (bool): If set to
        True, raise an error if executable not found

    Returns:
      exe: The first executable that is found in the path

    """
    if path is not None:
        if isinstance(path, (list, tuple)):
            path = os.pathsep.join(path)
    else:
        path = os.getenv("PATH") or []

    paths: list[str]
    if isinstance(path, str):
        paths = path.split(os.pathsep)
    else:
        paths.extend(path)

    for name in args:
        exe = os.path.abspath(name)
        if os.path.isfile(exe) and os.access(exe, os.X_OK):
            return exe
        for directory in paths:
            exe = os.path.join(directory, name)
            if os.path.isfile(exe) and os.access(exe, os.X_OK):
                return exe

    if required:
        raise FileNotFoundError(args[0])

    return None


def copyfile(src: str, dst: str) -> None:
    """Copy file `src` to `dst`"""
    if os.path.isdir(dst):
        basename = os.path.basename(src)
        dst = os.path.join(dst, basename)
    shutil.copy(src, dst)


def movefile(src: str, dst: str) -> None:
    """Move file `src` to `dst`"""
    shutil.move(src, dst)


def synctree(
    src: str,
    dst: str,
    ignore: str | list | tuple | None = None,
    delete: bool = False,
    verbose: bool = False,
    **kwargs: Any,
):
    """Sync source directory ``src`` with destination directory ``dst``"""
    from .executable import Executable

    f = which("rsync", required=True)
    assert isinstance(f, str)
    rsync = Executable(f)

    src = os.path.normpath(src)
    dst = os.path.normpath(dst)
    if os.path.exists(dst):
        src += os.path.sep
        dst += os.path.sep

    args = ["-arz"]
    if ignore is not None:
        if isinstance(ignore, str):
            ignore = shlex.split(ignore)
        for item in ignore:
            args.extend(["--exclude", item])
    if delete:
        args.append("--delete")
    if verbose:
        args.append("-v")
    args.extend([src, dst])
    rsync(*args, **kwargs)
    return rsync.returncode


def force_remove(file_or_dir: str) -> None:
    """Remove ``file_or_dir`` forcefully"""
    try:
        remove(file_or_dir)
    except Exception:
        pass


def force_copy(src: str, dst: str, echo: Callable = lambda x: None) -> None:
    """Forcefully copy ``src`` to ``dst``"""
    echo(f"copy {src} -> {dst}\n")
    if os.path.isfile(src):
        remove(dst)
        copyfile(src, dst)
    elif os.path.isdir(src):
        remove(dst)
        shutil.copytree(src, dst)
    else:
        raise ValueError(f"force_copy: file not found: {src}")


def remove(file_or_dir: pathlib.Path | str) -> None:
    """Removes file or directory ``file_or_dir``"""
    path = pathlib.Path(file_or_dir)
    if path.is_symlink():
        os.unlink(path)
    elif path.is_dir():
        rmtree2(path)
    elif path.exists():
        os.remove(path)


def rmtree2(path: pathlib.Path | str, n: int = 5) -> None:
    """Wrapper around shutil.rmtree to make it more robust when used on NFS
    mounted file systems."""
    ok = False
    attempts = 1
    while not ok:
        try:
            shutil.rmtree(path)
            ok = True
        except OSError as e:
            if attempts >= n:
                raise
            logging.debug(f"Failed to remove {path} with shutil.rmtree at attempt {n}: {e}")
            time.sleep(0.2 * n)
        attempts += 1


def getuser() -> str:
    """Return the name of the logged on user"""
    try:
        return getpass.getuser()
    except Exception:  # pragma: no cover
        home = os.path.expanduser("~")
        if home != "~":
            return os.path.basename(home)
        return os.getenv("USER", os.getenv("LOGNAME"))  # type: ignore


def gethost() -> str:
    """Return the host name of the machine, as reported by os.uname().nodename"""
    return os.uname().nodename


getnode = gethost


def gettempdir(user: bool = False, suffix: str | None = None) -> str:
    """Get the name of the system's preferred temporary directory. If `user`
    is given, postfix the directory with the user name"""
    tempdir = tempfile.gettempdir()
    if user:
        tempdir = os.path.join(tempdir, getuser())
    if suffix:
        tempdir = os.path.join(tempdir, suffix)
    return tempdir


@contextmanager
def tmpdir(remove: bool = True, suffix: str | None = None) -> Generator[str, None, None]:
    """Create a temporary directory and remove it when the context is exited

    Keyword Args:
      remove: remove the temporary directory when the context is exited
      suffix: added to the end of the directory name

    Examples:

      >>> with tmpdir():
      ...    # do work in temporary directory

    """
    dirname = gettempdir(user=True, suffix=suffix)
    try:
        mkdirp(dirname)
        yield dirname
    finally:
        if remove:
            rmtree2(dirname)


def gethome() -> str:
    """Return the home directory of the currently logged in user"""
    return os.path.expanduser("~")


def filesize(filename: str, *, units: str | None = None) -> int:
    r"""Return ``filename``\ 's size.  If ``units`` is ``None``, the size in bytes is returned.
    Valid ``units`` are ``kilobytes``, ``megabytes``, and ``gigabytes``.

    """
    size_in_bytes = os.path.getsize(filename)
    if units == "kilobytes":
        return int(size_in_bytes / 1024)
    elif units == "megabytes":
        return int(size_in_bytes / 1024 / 1024)
    elif units == "gigbytes":
        return int(size_in_bytes / 1024 / 1024 / 1024)
    else:
        return size_in_bytes


def git_revision(path: str) -> str:
    """Get the git revision at ``path``.  Equivalent to ``git -C path rev-parse HEAD``"""
    from .executable import Executable

    f = which("git", required=True)
    assert isinstance(f, str)
    git = Executable(f)
    with working_dir(path):
        result = git("rev-parse", "HEAD", output=str)
        return result.get_output()


def file_age_in_days(file: str) -> float:
    r"""Return the ``file``\ 's age in days"""
    now = datetime.datetime.now(datetime.timezone.utc)
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(file), datetime.timezone.utc)
    delta = now - mtime
    return delta.days


def sortby_mtime(files: list[str]) -> list[str]:
    """Sort the list of ``files`` by ``mtime``."""
    return sorted(files, key=os.path.getmtime)


def touch(path: str) -> None:
    """Creates an empty file at the specified path."""
    perms = os.O_WRONLY | os.O_CREAT | os.O_NONBLOCK | os.O_NOCTTY
    fd = None
    try:
        fd = os.open(path, perms)
        os.utime(path, None)
    finally:
        if fd is not None:
            os.close(fd)


def touchp(path: str) -> None:
    """Like ``touch``, but creates any parent directories needed for the file."""
    mkdirp(os.path.dirname(os.path.abspath(path)))
    touch(path)


@contextmanager
def working_dir(dirname: str, create: bool = False) -> Generator[None, None, None]:
    """Context manager that changes the working directory to ``dirname`` and returns to the calling
    directory when the context is exited"""
    if create:
        mkdirp(dirname)

    orig_dir = os.getcwd()
    os.chdir(dirname)
    yield
    os.chdir(orig_dir)


def mkdirp(*paths: str, mode: int | None = None) -> None:
    """Creates a directory, as well as parent directories if needed.

    Arguments:
        paths (str): paths to create with mkdirp

    Keyword Aguments:
        mode (permission bits or None, optional): optional permissions to
            set on the created directory -- use OS default if not provided
    """
    for path in paths:
        if not os.path.exists(path):
            try:
                os.makedirs(path)
                if mode is not None:
                    os.chmod(path, mode)
            except OSError as e:
                if e.errno != errno.EEXIST or not os.path.isdir(path):
                    raise e
        elif not os.path.isdir(path):
            raise OSError(errno.EEXIST, "File already exists", path)


def set_executable(path: str) -> None:
    """Set executable bits on ``path``"""
    mode = os.stat(path).st_mode
    if mode & stat.S_IRUSR:
        mode |= stat.S_IXUSR
    if mode & stat.S_IRGRP:
        mode |= stat.S_IXGRP
    if mode & stat.S_IROTH:
        mode |= stat.S_IXOTH
    os.chmod(path, mode)


def is_exe(path: str) -> bool:
    """True if path is an executable file."""
    return os.path.isfile(path) and os.access(path, os.X_OK)


def force_symlink(src: str, dest: str, echo: Callable = lambda x: None) -> None:
    """Forcefully create a symbolic link from ``src`` to ``dest``"""
    echo(f"link {src} -> {dest}\n")
    try:
        os.symlink(src, dest)
    except (OSError, FileExistsError):
        remove(dest)
        os.symlink(src, dest)


def accessible(file_name: str) -> bool:
    """True if we have read/write access to the file."""
    return os.access(file_name, os.R_OK | os.W_OK)


def readable(file_name: str) -> bool:
    """True if we have read access to the file."""
    return os.access(file_name, os.R_OK)


def writeable(file_name: str) -> bool:
    """True if we have write access to the file."""
    return os.access(file_name, os.W_OK)


def chgrp(path: str, group: str) -> None:
    """Implement the bash chgrp function on a single path"""
    if isinstance(group, str):
        gid = grp.getgrnam(group).gr_gid
    else:
        gid = group
    os.chown(path, -1, gid)


def chmod_x(entry: str, perms: int) -> None:
    """Implements chmod, treating all executable bits as set using the chmod
    utility's `+X` option.
    """
    mode = os.stat(entry).st_mode
    if os.path.isfile(entry):
        if not mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
            perms &= ~stat.S_IXUSR
            perms &= ~stat.S_IXGRP
            perms &= ~stat.S_IXOTH
    os.chmod(entry, perms)


def samepath(path1: str, path2: str) -> bool:
    """Does ``path1`` point to the same path as ``path2``?"""
    return os.path.normpath(path1) == os.path.normpath(path2)


def ancestor(dir: str, n: int = 1) -> str:
    """Get the nth ancestor of a directory."""
    parent = os.path.abspath(dir)
    for i in range(n):
        parent = os.path.dirname(parent)
    return parent


def grep(regex: str | re.Pattern, file: str) -> bool:
    rx: re.Pattern = re.compile(regex) if isinstance(regex, str) else regex
    try:
        for line in open(file):
            if rx.search(line):
                return True
    except UnicodeDecodeError:
        pass
    return False


def find_work_tree(start: str | None = None) -> str | None:
    path = os.path.abspath(start or os.getcwd())
    tagfile = "SESSION.TAG"
    while True:
        if os.path.exists(os.path.join(path, tagfile)):
            return os.path.dirname(path)
        elif os.path.exists(os.path.join(path, ".canary", tagfile)):
            return path
        path = os.path.dirname(path)
        if path == os.path.sep:
            break
    return None
