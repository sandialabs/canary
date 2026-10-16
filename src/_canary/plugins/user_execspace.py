# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Run jobs under an alternate execution prefix and migrate results back.

``canary run --exec-prefix=PATH`` executes every job of the session in a
location below ``PATH`` (for example a node-local RAM disk or a burst buffer
such as ``/beeond/$USER``) instead of the session directory inside the
workspace.  When the session finishes, each job's execution directory is copied
back to its normal location in the session directory.  The tree below ``PATH``
is left in place; its lifetime is up to the user or the system providing it.

The feature is implemented entirely with hooks:

``canary_addoption``
    Registers ``--exec-prefix`` on ``canary run``.

``canary_runtests_start``
    Redirects each job's :class:`~_canary.execution.testexec.ExecutionSpace` so
    that ``job.workspace.dir`` resolves below the prefix.  The redirect happens
    in the process that drives execution, before worker processes are started,
    so workers and the executor (which records results for jobs that time out or
    whose worker dies) agree on where each job lives.  Job setup then links or
    copies test assets into the prefix as usual.

``canary_runtests_finish``
    Runs after every job has a terminal status and before any reporter.  Copies
    each job directory back (``testcase.lock`` last), restores the job's
    execution space and environment to the session directory, rewrites the lock
    file with host paths, and refreshes the results view.

Layout below the prefix::

    <prefix>/canary/<workspace-hash>/<session>/<job exec path>

The workspace hash keeps concurrent workspaces (and sessions) that share a
prefix from colliding.  Environment variables and ``~`` in the prefix are
expanded in the process that runs the jobs, so a quoted ``'$USER'`` resolves on
the execution host.

The redirect applies to the process in which ``canary_runtests_start`` fires
with the option set.  A plugin that replaces ``canary_runtests`` to dispatch
jobs to another process or host is responsible for forwarding
``exec_prefix`` to the process that executes the jobs and clearing it locally.
"""

import dataclasses
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from .. import config
from ..util import logging
from ..util.hash import hashit
from .hookspec import hookimpl

if TYPE_CHECKING:
    from ..config.argparsing import Parser
    from ..core.job import Job
    from ..execution.runtest import Runner


logger = logging.get_logger(__name__)

#: Environment variable providing a default for ``--exec-prefix``.
EXEC_PREFIX_ENV = "CANARY_EXEC_PREFIX"

#: Job variables whose leading entry is the job's execution directory
#: (see ``Job.get_environ_from_spec``).
_DIR_VARIABLES = ("PATH", "PYTHONPATH")

_LOCKFILE = "testcase.lock"


@dataclasses.dataclass
class _Redirect:
    job: "Job"
    host_root: Path
    host_dir: Path
    exec_dir: Path


@dataclasses.dataclass
class _State:
    root: Path
    redirects: list[_Redirect]
    saved_cache_env: str | None
    set_cache_env: bool


#: Active redirect state for the session currently executing in this process.
_state: _State | None = None


def add_exec_prefix_option(parser: "Parser", command: str | list[str]) -> None:
    """Add ``--exec-prefix`` to the ``command`` subparser(s).

    Exposed so that plugins providing their own run-like subcommands can offer
    the same option.  Must be called from a ``canary_addoption`` implementation.
    """
    parser.add_argument(
        "--exec-prefix",
        dest="exec_prefix",
        metavar="PATH",
        command=command,
        group="execution location",
        default=os.getenv(EXEC_PREFIX_ENV) or None,
        help="Execute jobs below PATH (e.g. a node-local RAM disk or burst buffer) and copy "
        "their results back to the session directory when the session finishes. "
        "Environment variables in PATH are expanded when the jobs run "
        f"[default: ${EXEC_PREFIX_ENV}]",
    )


@hookimpl
def canary_addoption(parser: "Parser") -> None:
    add_exec_prefix_option(parser, command="run")


def resolve_prefix(raw: str) -> Path:
    """Expand ``~`` and environment variables in ``raw`` and return an absolute path.

    Raises:
        ValueError: if an environment variable could not be expanded.
    """
    expanded = os.path.expandvars(os.path.expanduser(raw))
    if "$" in expanded:
        raise ValueError(f"--exec-prefix={raw!r}: unresolved environment variable in {expanded!r}")
    return Path(os.path.abspath(expanded))


def session_exec_root(prefix: Path, workspace_root: Path, session: str) -> Path:
    """Return the per-session directory below ``prefix``."""
    tag = hashit(str(Path(workspace_root).absolute()), length=12)
    return prefix / "canary" / tag / session


@hookimpl(tryfirst=True)
def canary_runtests_start(runner: "Runner") -> None:
    global _state
    raw = config.getoption("exec_prefix")
    if not raw:
        return
    if _state is not None:
        raise RuntimeError("--exec-prefix: a redirected session is already active")
    prefix = resolve_prefix(str(raw))
    root = session_exec_root(prefix, runner.workspace.root, runner.session)
    for job in runner.jobs:
        host_dir = Path(job.workspace.dir).absolute()
        if _is_relative_to(root, host_dir) or _is_relative_to(host_dir, root):
            raise ValueError(
                f"--exec-prefix={raw!r}: execution root {root} overlaps the session "
                f"directory {host_dir}"
            )
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise ValueError(f"--exec-prefix={raw!r}: cannot create {root}: {e}") from e
    if not os.access(root, os.W_OK | os.X_OK):
        raise ValueError(f"--exec-prefix={raw!r}: {root} is not writable")

    # The runtime history store is located by walking up from the job's
    # workspace root to the workspace tag.  That walk fails below the prefix, so
    # pin the cache location for this process and the workers it spawns.
    saved = os.environ.get("CANARY_CACHE_DIR")
    set_cache_env = saved is None and not config.get("run:cache:dir")
    if set_cache_env:
        os.environ["CANARY_CACHE_DIR"] = str(Path(runner.workspace.root) / "cache")

    redirects: list[_Redirect] = []
    for job in runner.jobs:
        host_root = Path(job.workspace.root)
        host_dir = Path(job.workspace.dir)
        job.workspace.root = root
        exec_dir = Path(job.workspace.dir)
        _replace_dir_variables(job, old=host_dir, new=exec_dir)
        redirects.append(
            _Redirect(job=job, host_root=host_root, host_dir=host_dir, exec_dir=exec_dir)
        )
    _state = _State(
        root=root, redirects=redirects, saved_cache_env=saved, set_cache_env=set_cache_env
    )
    logger.info(f"[bold]Executing[/] {len(redirects)} jobs below {root}")


@hookimpl(tryfirst=True)
def canary_runtests_finish(runner: "Runner") -> None:
    global _state
    state, _state = _state, None
    if state is None:
        return
    try:
        for redirect in state.redirects:
            try:
                copy_back(redirect.exec_dir, redirect.host_dir, exec_root=state.root)
            except Exception as e:
                logger.error(
                    f"Failed to copy results of {redirect.job.display_name()} from "
                    f"{redirect.exec_dir} to {redirect.host_dir}: {e}"
                )
            finally:
                _restore(redirect, runner)
    finally:
        if state.set_cache_env:
            os.environ.pop("CANARY_CACHE_DIR", None)


def _restore(redirect: _Redirect, runner: "Runner") -> None:
    job = redirect.job
    job.workspace.root = redirect.host_root
    _replace_dir_variables(job, old=redirect.exec_dir, new=redirect.host_dir)
    if redirect.host_dir.exists():
        # Rewrite the lock so persisted paths refer to the session directory.
        try:
            job.save()
        except Exception:
            logger.debug(f"Failed to save {job.display_name()} after copy-back", exc_info=True)
    view_manager = getattr(runner.workspace, "view_manager", None)
    if view_manager is not None:
        try:
            view_manager.sync(job)
        except Exception:
            logger.debug(f"Failed to update view for {job.display_name()}", exc_info=True)


def copy_back(src: Path, dst: Path, *, exec_root: Path) -> bool:
    """Copy the execution directory ``src`` to ``dst``.

    ``dst`` is replaced, mirroring ``Job.setup`` which recreates the execution
    directory from scratch.  Symbolic links are preserved; absolute links that
    point inside ``exec_root`` are rewritten to the corresponding location below
    ``dst``'s session directory.  The job lock file is copied last, atomically,
    so a reader never sees a finished job whose outputs are still in flight.

    Returns:
        ``False`` if ``src`` does not exist (nothing to copy), else ``True``.
    """
    src, dst = Path(src), Path(dst)
    if not src.is_dir():
        return False
    if dst.is_symlink() or dst.is_file():
        dst.unlink()
    elif dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    def ignore(directory: str, names: list[str]) -> list[str]:
        return [_LOCKFILE] if Path(directory) == src and _LOCKFILE in names else []

    shutil.copytree(src, dst, symlinks=True, ignore=ignore, copy_function=shutil.copy2)
    host_root = _host_root_for(src, dst, exec_root)
    if host_root is not None:
        _rewrite_symlinks(dst, old=exec_root, new=host_root)
    lock = src / _LOCKFILE
    if lock.exists():
        tmp = dst / f".{_LOCKFILE}.{os.getpid()}.tmp"
        shutil.copy2(lock, tmp)
        os.replace(tmp, dst / _LOCKFILE)
    return True


def _host_root_for(src: Path, dst: Path, exec_root: Path) -> Path | None:
    """Return the session directory corresponding to ``exec_root``."""
    try:
        rel = src.relative_to(exec_root)
    except ValueError:
        return None
    root = dst
    for _ in rel.parts:
        root = root.parent
    return root


def _rewrite_symlinks(top: Path, *, old: Path, new: Path) -> None:
    for dirpath, dirnames, filenames in os.walk(top):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            if not path.is_symlink():
                continue
            target = Path(os.readlink(path))
            if target.is_absolute() and _is_relative_to(target, old):
                path.unlink()
                path.symlink_to(new / target.relative_to(old))


def _replace_dir_variables(job: "Job", *, old: Path, new: Path) -> None:
    variables: dict[str, Any] = job.variables
    old_s, new_s = str(old), str(new)
    for key in _DIR_VARIABLES:
        value = variables.get(key)
        if not isinstance(value, str):
            continue
        if value == old_s:
            variables[key] = new_s
        elif value.startswith(old_s + os.pathsep):
            variables[key] = new_s + value[len(old_s) :]


def _is_relative_to(path: Path, other: Path) -> bool:
    try:
        Path(path).relative_to(other)
    except ValueError:
        return False
    return True
