# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import time

from ... import config
from ...generator import AbstractTestGenerator
from ...util import logging
from ...util.executable import Executable
from ...util.filesystem import working_dir
from ..hookspec import hookimpl

skip_dirs = ["__nvcache__", "__pycache__", ".git", ".svn", ".canary"]


logger = logging.get_logger(__name__)


@hookimpl(trylast=True)
def canary_discover_generators(
    root: str, paths: list[str] | None
) -> tuple[list[AbstractTestGenerator], int]:
    relroot = os.path.relpath(root, config.invocation_dir)
    generators: list[AbstractTestGenerator] = []
    errors: int = 0

    created = time.monotonic()
    msg = "@*{Searching} %s for test generators" % relroot
    logger.log(logging.INFO, msg, extra={"end": "..."})
    try:
        if os.path.isfile(root):
            try:
                f = AbstractTestGenerator.factory(root)
            except Exception as e:
                errors += 1
                logger.exception(f"Failed to parse {root}")
            else:
                generators.append(f)
        elif root.startswith(("git@", "repo@")):
            found, p_errors = vcfind(root)
            generators.extend(found)
            errors += p_errors
        elif paths is not None:
            for path in paths:
                p = os.path.join(root, path)
                if os.path.isfile(p):
                    try:
                        f = AbstractTestGenerator.factory(root, path)
                    except Exception as e:
                        errors += 1
                        logger.exception(f"Failed to parse {root}/{path}")
                    else:
                        generators.append(f)
                elif os.path.isdir(p):
                    found, p_errors = rfind(root, subdir=path)
                    generators.extend(found)
                    errors += p_errors
                else:
                    errors += 1
                    logger.error(f"No such file: {path}")
        else:
            found, p_errors = rfind(root)
            generators.extend(found)
            errors += p_errors
    except Exception:
        state = "failed"
        raise
    else:
        state = "done"
    finally:
        end = "... %s (%.2fs.)\n" % (state, time.monotonic() - created)
        extra = {"end": end, "rewind": True}
        logger.log(logging.INFO, msg, extra=extra)

    return generators, errors


def vcfind(root: str) -> tuple[list[AbstractTestGenerator], int]:
    """Find files in version control repository (only git supported)"""
    type, _, root = root.partition("@")
    files: list[str]
    if type == "git":
        files = git_ls(root)
    elif type == "repo":
        files = repo_ls(root)
    else:
        logger.error("Unknown vc type {type!r}, choose from git, repo")
        return [], 1
    errors: int = 0
    generators: list[AbstractTestGenerator] = []
    with working_dir(root):
        for file in files:
            try:
                if generator := config.plugin_manager.hook.canary_testcase_generator(
                    root=root, path=file
                ):
                    generators.append(generator)
            except Exception as e:
                errors += 1
                logger.exception(f"Failed to parse {root}/{file}")
    return generators, errors


def rfind(root: str, subdir: str | None = None) -> tuple[list[AbstractTestGenerator], int]:
    def skip(directory):
        if os.path.basename(directory).startswith("."):
            return True
        elif os.path.basename(directory) in skip_dirs:
            return True
        if os.path.exists(os.path.join(directory, ".canary/SESSION.TAG")):
            return True
        return False

    start = root if subdir is None else os.path.join(root, subdir)
    errors: int = 0
    generators: list[AbstractTestGenerator] = []
    for dirname, dirs, files in os.walk(start):
        if skip(dirname):
            del dirs[:]
            continue
        try:
            for f in files:
                file = os.path.join(dirname, f)
                generator: AbstractTestGenerator | None
                try:
                    if generator := config.plugin_manager.hook.canary_testcase_generator(
                        root=root, path=os.path.relpath(file, root)
                    ):
                        generators.append(generator)
                except Exception as e:
                    errors += 1
                    logger.exception(f"Failed to parse {file}")
                else:
                    if generator and generator.stop_recursion():
                        raise StopRecursion
        except StopRecursion:
            del dirs[:]
            continue
    return generators, errors


def git_ls(root: str) -> list[str]:
    git = Executable("git")
    with working_dir(root):
        result = git("ls-files", "--recurse-submodules", stdout=str)
    return [f.strip() for f in result.get_output().split("\n") if f.split()]


def repo_ls(root: str) -> list[str]:
    repo = Executable("repo")
    with working_dir(root):
        result = repo("-c", "git ls-files --recurse-submodules", stdout=str)
    return [f.strip() for f in result.get_output().split("\n") if f.split()]


class StopRecursion(Exception):
    pass
