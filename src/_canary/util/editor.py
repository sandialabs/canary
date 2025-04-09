# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Module for finding the user's preferred text editor.

Defines one function, editor(), which invokes the editor defined by the
user's VISUAL environment variable if set. We fall back to the editor
defined by the EDITOR environment variable if VISUAL is not set or the
specified editor fails (e.g. no DISPLAY for a graphical editor). If
neither variable is set, we fall back to one of several common editors,
raising an EnvironmentError if we are unable to find one.

This file was adapted from spack.util.editor

"""

import os
import shlex
from types import SimpleNamespace
from typing import Callable

import _canary.config as config
from _canary.util import logging
from _canary.util.filesystem import which

#: editors to try if VISUAL and EDITOR are not set
_default_editors = ["vim", "vi", "emacs", "nano", "notepad", "code"]


def _find_exe_from_env_var(var: str) -> SimpleNamespace | None:
    """Find an executable from an environment variable.

    Args:
        var: environment variable name

    Returns:
        (str or None, list): executable string (or None if not found) and
            arguments parsed from the env var
    """
    # try to get the environment variable
    path = os.getenv(var)
    if path is None:
        return None

    # split env var into executable and args if needed
    args = shlex.split(path)
    if not args:
        return None

    path = which(args[0])
    if path is None:
        return None

    args[0] = path
    return SimpleNamespace(path=path, default_args=args)


def editor(*args_in: str, exec_fn: Callable[[str, list[str]], int] = os.execv) -> bool:
    """Invoke the user's editor.

    This will try to execute the following, in order:

      1. $VISUAL <args>    # the "visual" editor (per POSIX)
      2. $EDITOR <args>    # the regular editor (per POSIX)
      3. some default editor (see ``_default_editors``) with <args>

    If an environment variable isn't defined, it is skipped.  If it
    points to something that can't be executed, we'll print a
    warning. And if we can't find anything that can be executed after
    searching the full list above, we'll raise an error.

    Args:
        args_in: args to pass to editor

    Optional Arguments:
        exec_fn: invoke this function to run

    """

    def try_exec(path, args, var=None):
        """Try to execute an editor with execv, and warn if it fails.

        Returns: (bool) False if the editor failed, ideally does not
            return if ``execv`` succeeds, and ``True`` if the
            ``exec`` does return successfully.

        """
        # gvim runs in the background by default so we force it to run
        # in the foreground to ensure it gets attention.
        if "gvim" in path and "-f" not in args:
            args.insert(1, "-f")

        try:
            return exec_fn(path, args) == 0
        except OSError as e:
            if config.get("config:debug"):
                raise

            # Show variable we were trying to use, if it's from one
            p = path if var is None else f"${var} ({path})"
            logging.warning(f"Could not execute ${p} due to error: {e}")
            return False

    def try_env(var):
        """Find an editor from an environment variable and try to exec it.

        This will warn if the variable points to something is not
        executable, or if there is an error when trying to exec it.
        """
        if var not in os.environ:
            return False

        ns = _find_exe_from_env_var(var)
        if ns is None:
            logging.warning(f"${var}={os.environ[var]} is not an executable")
            return False

        return try_exec(ns.path, ns.default_args + list(args_in), var)

    # try standard environment variables
    if try_env("VISUAL"):
        return True

    if try_env("EDITOR"):
        return True

    # nothing worked -- try the first default we can find don't bother trying them all -- if we get
    # here and one fails, something is probably much more deeply wrong with the environment.
    path = which(*_default_editors)
    if path and try_exec(path, [path] + list(args_in)):
        return True

    # Fail if nothing could be found
    raise ValueError(
        "No text editor found! Please set the VISUAL and/or EDITOR "
        "environment variable(s) to your preferred text editor."
    )
