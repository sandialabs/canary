import errno
import getpass
import grp
import os
import pathlib
import shlex
import shutil
import stat
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Union

from . import tty

__all__ = [
    "ancestor",
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
]


def is_hidden(path):
    return os.path.basename(path).startswith(".")


def which(*args, path=None, required=False):
    """Finds an executable in the path like command-line which.

    If given multiple executables, returns the first one that is found.
    If no executables are found, returns None.

    Parameters
    ----------
    args : (str)
        One or more executables to search for
    path : list or str
        The path to search. Defaults to ``PATH`` required (bool): If set to
        True, raise an error if executable not found

    Returns
    -------
    exe : str
        The first executable that is found in the path

    """
    if path is not None:
        if isinstance(path, (list, tuple)):
            path = os.pathsep.join(path)
    else:
        path = os.getenv("PATH") or []

    if isinstance(path, str):
        path = path.split(os.pathsep)

    for name in args:
        exe = os.path.abspath(name)
        if os.path.isfile(exe) and os.access(exe, os.X_OK):
            return exe
        for directory in path:
            exe = os.path.join(directory, name)
            if os.path.isfile(exe) and os.access(exe, os.X_OK):
                return exe

    if required:
        raise FileNotFoundError(args[0])

    return None


def copyfile(src, dst):
    """Copy file `src` to `dst`"""
    if os.path.isdir(dst):
        basename = os.path.basename(src)
        dst = os.path.join(dst, basename)
    shutil.copyfile(src, dst)


def movefile(src, dst):
    """Move file `src` to `dst`"""
    shutil.move(src, dst)


def synctree(src, dst, ignore=None, delete=False, verbose=False, **kwargs):
    """Wrapper around rsync"""
    from .executable import Executable

    f = which("rsync", required=True)
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


def force_remove(file_or_dir):
    try:
        return remove(file_or_dir)
    except Exception:
        pass


def force_copy(src, dst, echo=False):
    if echo:
        tty.emit(f"link {src} -> {dst}\n")
    if os.path.isfile(src):
        remove(dst)
        copyfile(src, dst)
    elif os.path.isdir(src):
        remove(dst)
        shutil.copytree(src, dst)
    else:
        raise ValueError(f"force_copy: file not found: {src}")


def remove(file_or_dir: Union[pathlib.Path, str]):
    """Removes file or directory `file_or_dir`"""
    path = pathlib.Path(file_or_dir)
    if path.is_symlink():
        os.remove(path)
    elif path.is_dir():
        rmtree2(path)
    elif path.exists():
        os.remove(path)


def rmtree2(path, n=5):
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
            tty.debug(f"Failed to remove {path} with shutil.rmtree at attempt {n}: {e}")
            time.sleep(0.2 * n)
        attempts += 1


def getuser():
    """Return the name of the logged on user"""
    try:
        return getpass.getuser()
    except:  # noqa: E722; pragma: no cover
        home = os.path.expanduser("~")
        if home != "~":
            return os.path.basename(home)
        return os.getenv("USER", os.getenv("LOGNAME"))


def gethost():
    """Return the host name of the machine, as reported by os.uname().nodename"""
    return os.uname().nodename


getnode = gethost


def gettempdir(user=False, suffix=None):
    """Get the name of the system's preferred temporary directory. If `user`
    is given, postfix the directory with the user name"""
    tempdir = tempfile.gettempdir()
    if user:
        tempdir = os.path.join(tempdir, getuser())
    if suffix:
        tempdir = os.path.join(tempdir, suffix)
    return tempdir


@contextmanager
def tmpdir(remove=True, suffix=None):
    dirname = gettempdir(user=True, suffix=suffix)
    mkdirp(dirname)
    yield dirname
    if remove:
        rmtree2(dirname)


def gethome():
    """Return the home directory of the currently logged in user"""
    return os.path.expanduser("~")


def filesize(filename, *, units=None):
    size_in_bytes = os.path.getsize(filename)
    if units == "kilobytes":
        return size_in_bytes / 1024
    elif units == "megabytes":
        return size_in_bytes / 1024 / 1024
    elif units == "gigbytes":
        return size_in_bytes / 1024 / 1024 / 1024
    else:
        return size_in_bytes


def git_revision(path):
    from .executable import Executable

    f = which("git", required=True)
    git = Executable(f)
    with working_dir(path):
        return git("rev-parse", "HEAD", output=str).strip()


def file_age_in_days(file):
    now = datetime.utcnow()
    mtime = datetime.utcfromtimestamp(os.path.getmtime(file))
    delta = now - mtime
    return delta.days


def sortby_mtime(files):
    return sorted(files, key=os.path.getmtime)


def touch(path):
    """Creates an empty file at the specified path."""
    perms = os.O_WRONLY | os.O_CREAT | os.O_NONBLOCK | os.O_NOCTTY
    fd = None
    try:
        fd = os.open(path, perms)
        os.utime(path, None)
    finally:
        if fd is not None:
            os.close(fd)


def touchp(path):
    """Like ``touch``, but creates any parent directories needed for the file."""
    mkdirp(os.path.dirname(os.path.abspath(path)))
    touch(path)


@contextmanager
def working_dir(dirname, **kwargs):
    if kwargs.get("create", False):
        mkdirp(dirname)

    orig_dir = os.getcwd()
    os.chdir(dirname)
    yield
    os.chdir(orig_dir)


def mkdirp(*paths, **kwargs):
    """Creates a directory, as well as parent directories if needed.

    Arguments:
        paths (str): paths to create with mkdirp

    Keyword Aguments:
        mode (permission bits or None, optional): optional permissions to
            set on the created directory -- use OS default if not provided
    """
    mode = kwargs.get("mode", None)
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


def set_executable(path):
    mode = os.stat(path).st_mode
    if mode & stat.S_IRUSR:
        mode |= stat.S_IXUSR
    if mode & stat.S_IRGRP:
        mode |= stat.S_IXGRP
    if mode & stat.S_IROTH:
        mode |= stat.S_IXOTH
    os.chmod(path, mode)


def is_exe(path):
    """True if path is an executable file."""
    return os.path.isfile(path) and os.access(path, os.X_OK)


def force_symlink(src, dest, echo=False):
    if echo:
        tty.emit(f"link {src} -> {dest}\n")
    try:
        os.symlink(src, dest)
    except OSError:
        remove(dest)
        os.symlink(src, dest)


def accessible(file_name: str) -> bool:
    """True if we have read/write access to the file."""
    return os.access(file_name, os.R_OK | os.W_OK)


def readable(file_name: str) -> bool:
    return os.access(file_name, os.R_OK)


def writeable(file_name: str) -> bool:
    return os.access(file_name, os.W_OK)


def chgrp(path, group):
    """Implement the bash chgrp function on a single path"""
    if isinstance(group, str):
        gid = grp.getgrnam(group).gr_gid
    else:
        gid = group
    os.chown(path, -1, gid)


def chmod_x(entry, perms):
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


def samepath(path1, path2):
    return os.path.normpath(path1) == os.path.normpath(path2)


def ancestor(dir, n=1):
    """Get the nth ancestor of a directory."""
    parent = os.path.abspath(dir)
    for i in range(n):
        parent = os.path.dirname(parent)
    return parent
