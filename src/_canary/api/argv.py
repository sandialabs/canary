# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Map pydantic request models onto canary's parser: each field names an argparse dest.

Each field of a work request model is annotated with ``Dest("argparse_dest")``.
:func:`defaults` and :func:`to_options` fill canary's options object from such a model
through the parser's own actions -- the same namespace ``canary ...`` parses to, without
building a command line.
"""

import argparse

from pydantic import BaseModel

#: Dests a request may never set: they would wipe the workspace, read paths from a file
#: on the server, or move the work tree.
DENIED = frozenset({"wipe_workspace", "f_pathspec", "work_tree"})


def denied(action: argparse.Action) -> bool:
    """True if no request may set *action* (see :data:`DENIED`; deprecated actions too)."""
    return action.dest in DENIED or type(action).__name__.startswith("Deprecated")


class Dest:
    """Marker for mapping a pydantic field to an argparse action dest."""

    def __init__(self, dest: str):
        self.dest = dest


def defaults(parser: argparse.ArgumentParser, *command: str) -> argparse.Namespace:
    """The namespace ``canary COMMAND`` parses to with no further arguments.

    Every option's default, the main parser's and each subcommand's (the subcommand's
    win, as in argparse), with the subcommand dests (``command``, ...) set -- without a
    command line and without running any action.
    """
    ns = argparse.Namespace()
    current = parser
    chain = [parser]
    for name in command:
        sub = next(a for a in current._actions if isinstance(a, argparse._SubParsersAction))
        setattr(ns, sub.dest, name)
        current = sub.choices[name]
        chain.append(current)
    for p in chain:
        for action in p._actions:
            if isinstance(action, argparse._SubParsersAction) or action.dest == argparse.SUPPRESS:
                continue
            if action.default is argparse.SUPPRESS:
                continue
            value = action.default
            if isinstance(value, str):
                value = p._get_value(action, value)  # as argparse converts string defaults
            setattr(ns, action.dest, value)
        for key, value in p._defaults.items():
            setattr(ns, key, value)
    return ns


def to_options(model: BaseModel, parser: argparse.ArgumentParser, ns: argparse.Namespace) -> None:
    """Set *model*'s fields on *ns* through the actions of the subcommand *parser*.

    Each field is applied by calling its action, as argparse does once it has the
    argument's value, so custom actions (the pathspec, ``--timeout``, ``--view``) do their
    own work; no command line is built.  Positionals are applied even when empty, as
    argparse does.  Raises ``ValueError`` naming the field when an action refuses a value.
    """
    actions = {a.dest: a for a in parser._actions if a.dest != "help"}
    for field_name, field_info in type(model).model_fields.items():
        dest = next((m.dest for m in field_info.metadata if isinstance(m, Dest)), None)
        if dest is None:
            continue
        if dest not in actions:
            raise ValueError(f"Field '{field_name}' maps to dest '{dest}', which the parser lacks")
        action = actions[dest]
        if denied(action):
            raise ValueError(f"Field '{field_name}' maps to dest '{dest}', which is denied")
        value = getattr(model, field_name)
        try:
            _apply(action, parser, ns, value)
        except argparse.ArgumentError as exc:  # its str() leads with the CLI's metavar
            raise ValueError(f"{field_name}: {exc.message}") from None
        except ValueError as exc:
            raise ValueError(f"{field_name}: {exc}") from None


def _apply(action: argparse.Action, parser: argparse.ArgumentParser, ns, value) -> None:
    if not action.option_strings:
        action(parser, ns, list(value) if isinstance(value, list) else [value], None)
        return
    if value is None or value is False or (isinstance(value, list) and not value):
        return
    flag = action.option_strings[-1]
    if action.nargs == 0:
        action(parser, ns, None, flag)
        return
    for item in value if isinstance(value, list) else [value]:
        action(parser, ns, item, flag)
