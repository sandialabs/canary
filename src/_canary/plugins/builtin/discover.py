# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

from ... import config
from ...generator import AbstractTestGenerator
from ...third_party.color import colorize
from ...util import logging
from ...util.executable import Executable
from ...util.filesystem import working_dir
from ..hookspec import hookimpl

skip_dirs = ["__nvcache__", "__pycache__", ".git", ".svn", ".canary"]


@hookimpl(trylast=True)
def canary_discover_generators(
    root: str, paths: list[str] | None
) -> tuple[list[AbstractTestGenerator], int]:
    relroot = os.path.relpath(root, config.invocation_dir)
    generators: list[AbstractTestGenerator] = []
    errors: int = 0
    with logging.context(colorize("@*{Searching} %s for test generators" % relroot)):
        if os.path.isfile(root):
            try:
                f = AbstractTestGenerator.factory(root)
            except Exception as e:
                errors += 1
                logging.exception(f"Failed to parse {root}", e)
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
                        logging.exception(f"Failed to parse {root}/{path}", e)
                    else:
                        generators.append(f)
                elif os.path.isdir(p):
                    found, p_errors = rfind(root, subdir=path)
                    generators.extend(found)
                    errors += p_errors
                else:
                    errors += 1
                    logging.error(f"No such file: {path}")
        else:
            found, p_errors = rfind(root)
            generators.extend(found)
            errors += p_errors
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
        logging.error("Unknown vc type {type!r}, choose from git, repo")
        return [], 1
    errors: int = 0
    generators: list[AbstractTestGenerator] = []
    with working_dir(root):
        gen_types = config.plugin_manager.get_generators()
        for file in files:
            for gen_type in gen_types:
                if gen_type.matches(file):
                    try:
                        generators.append(gen_type(root, file))
                    except Exception as e:
                        errors += 1
                        logging.exception(f"Failed to parse {root}/{file}", e)
                    break
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
    gen_types = config.plugin_manager.get_generators()
    generators: list[AbstractTestGenerator] = []
    for dirname, dirs, files in os.walk(start):
        if skip(dirname):
            del dirs[:]
            continue
        try:
            for f in files:
                file = os.path.join(dirname, f)
                for gen_type in gen_types:
                    if gen_type.matches(file):
                        try:
                            generator = gen_type(root, os.path.relpath(file, root))
                        except Exception as e:
                            errors += 1
                            logging.exception(f"Failed to parse {file}", e)
                        else:
                            generators.append(generator)
                            if generator.stop_recursion():
                                raise StopRecursion
                        break
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
