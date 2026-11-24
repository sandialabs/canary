# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""The models of the endpoints that still become command lines, against canary's parser.

``/canary/run`` and ``/canary/hpc/run`` (plan D2); the other work endpoints call
``_canary.app`` (D6) and are tested in work_endpoints.py.
"""

import argparse
import typing

import pytest

import canary
from _canary.api.argv import Dest
from _canary.api.argv import defaults
from _canary.api.argv import denied
from _canary.api.argv import to_options
from _canary.api.dispatch import build_registry
from _canary.api.work import options_for
from _canary.api.work import parser
from _canary.workspace.workspace import Workspace


# The command line equivalent to a request (how the CLI would say it), to compare the
# options the API fills with what `canary ...` parses.  Not production code: the API never
# builds a command line.
def to_argv(model, parser: argparse.ArgumentParser) -> list[str]:
    """Convert a pydantic model to command-line arguments using the real parser.

    Args:
        model: Pydantic request model with Dest annotations
        parser: The subcommand's argparse parser (from Parser.get_subparser)

    Returns:
        List of command-line arguments ready to pass to the parser

    Raises:
        ValueError: If a field's dest is not found in the parser, or if
                    the field value doesn't match the action type
    """
    # Build a map from dest -> action
    dest_to_action: dict[str, argparse.Action] = {}
    for action in parser._actions:
        if action.dest != "help":
            dest_to_action[action.dest] = action

    args: list[str] = []
    positionals: list[tuple[int, list[str]]] = []  # (position_in_parser, values)

    # Iterate through model fields
    for field_name, field_info in model.__class__.model_fields.items():
        value = getattr(model, field_name)

        # Skip unset optional fields
        if value is None or (isinstance(value, list) and len(value) == 0):
            continue

        # Extract Dest from pydantic field metadata
        dest_name = None
        for meta in field_info.metadata:
            if isinstance(meta, Dest):
                dest_name = meta.dest
                break

        if not dest_name:
            # No Dest annotation, skip this field
            continue

        # Look up the action
        if dest_name not in dest_to_action:
            raise ValueError(
                f"Field '{field_name}' maps to dest '{dest_name}', "
                f"but no action with that dest exists in the parser"
            )

        action = dest_to_action[dest_name]
        if denied(action):
            raise ValueError(f"Field '{field_name}' maps to dest '{dest_name}', which is denied")

        # Handle positional arguments separately
        if not action.option_strings:
            # Positional argument
            position = parser._actions.index(action)
            if isinstance(value, list):
                positionals.append((position, value))
            else:
                positionals.append((position, [str(value)]))
            continue

        flag = action.option_strings[-1]
        if action.nargs == 0:
            if value is True:
                args.append(flag)
            continue
        # One flag per value (an append action repeats); the value is attached to the flag
        # so one starting with '-' (e.g. '--partition=debug') is not read as an option.
        for item in value if isinstance(value, list) else [value]:
            args.append(f"{flag}={item}" if flag.startswith("--") else f"{flag}{item}")

    # Append positionals in order
    for _, values in sorted(positionals):
        args.extend(values)

    return args


def command_line(request, *command: str) -> list[str]:
    return [*command, *to_argv(request, parser().get_subparser("::".join(command)))]


WORK = [e for e in build_registry() if e.path in ("/canary/run", "/canary/hpc/run")]

#: Every field of every work model set, as a caller would.
FULL = {
    "/canary/run": {
        "pathspec": ["tests"],
        "keyword": "fast",
        "owner": "alice",
        "parameter": "cpus<8",
        "regex": "foo",
        "only": "failed",
        "on_options": ["dbg", "opt"],
        "workers": 2,
        "timeout": "session=10m",
        "fail_fast": True,
        "view": "mode=symlink",
    },
    "/canary/hpc/run": {
        "pathspec": ["tests"],
        "backend": "slurm",
        "keyword": "fast",
        "owner": "alice",
        "parameter": "cpus<8",
        "regex": "foo",
        "only": "failed",
        "on_options": ["dbg"],
        "workers": 2,
        "timeout": "session=10m",
        "fail_fast": True,
        "view": "mode=symlink",
        "batch_spec": "count=2",
        "batch_workers": 2,
        "submit_args": ["--partition=debug"],
        "allow_hyperthreading": True,
        "batch_exact_estimate": True,
    },
}
SEPARATE: dict[str, list[dict]] = {}


def _command(path: str) -> str:
    return "::".join(path.removeprefix("/canary/").split("/"))


def _fields(endpoint):
    """(name, annotation, dest) of each field of the endpoint's model."""
    hints = typing.get_type_hints(endpoint.model, include_extras=True)
    for name in endpoint.model.model_fields:
        dests = [m for m in typing.get_args(hints[name])[1:] if isinstance(m, Dest)]
        yield name, typing.get_args(hints[name])[0], dests[0].dest if dests else None


def _actions(path: str) -> dict[str, argparse.Action]:
    return {a.dest: a for a in parser().get_subparser(_command(path))._actions}


def test_every_work_endpoint_is_covered():
    assert sorted(e.path for e in WORK) == sorted(FULL)
    for endpoint in WORK:
        set_by_full = set(FULL[endpoint.path]).union(*map(set, SEPARATE.get(endpoint.path, [])))
        assert set_by_full == set(endpoint.model.model_fields), endpoint.path


@pytest.mark.parametrize("endpoint", WORK, ids=lambda e: e.path)
def test_every_field_maps_to_an_allowed_action_of_the_right_kind(endpoint):
    actions = _actions(endpoint.path)
    for name, annotation, dest in _fields(endpoint):
        assert dest is not None, f"{endpoint.path} {name} has no Dest"
        assert dest in actions, f"{endpoint.path} {name}: no action with dest {dest!r}"
        action = actions[dest]
        assert not denied(action), f"{endpoint.path} {name}: {dest} is denied"
        inner = [a for a in typing.get_args(annotation) if a is not type(None)] or [annotation]
        kind = inner[0]
        if kind is bool:
            assert action.nargs == 0, f"{endpoint.path} {name}: bool needs a flag with nargs=0"
        if typing.get_origin(kind) is list:
            assert isinstance(action, argparse._AppendAction) or not action.option_strings, (
                f"{endpoint.path} {name}: a list needs an append action or a positional"
            )
        if typing.get_origin(kind) is typing.Literal:
            assert list(typing.get_args(kind)) == list(action.choices or []), name
        elif action.choices is not None and not isinstance(action.choices, dict):
            pytest.fail(f"{endpoint.path} {name}: the parser has choices; use a Literal")


@pytest.mark.parametrize("endpoint", WORK, ids=lambda e: e.path)
def test_a_full_request_parses_with_the_real_parser(endpoint, tmp_path, monkeypatch):
    Workspace.create(tmp_path)
    (tmp_path / "tests").mkdir()
    monkeypatch.chdir(tmp_path)
    command = _command(endpoint.path).split("::")
    for body in [FULL[endpoint.path], *SEPARATE.get(endpoint.path, [])]:
        request = endpoint.model.model_validate(body)
        argv = command_line(request, *command)
        assert argv[: len(command)] == command
        parser().parse_args(argv)  # raises SystemExit on a bad command line


@pytest.mark.parametrize(
    "path, body",
    [
        ("/canary/run", FULL["/canary/run"]),
        ("/canary/run", {}),
        ("/canary/run", {"pathspec": ["tests"]}),
        ("/canary/hpc/run", FULL["/canary/hpc/run"]),
        ("/canary/hpc/run", {"backend": "local"}),
    ],
)
def test_work_fills_the_options_the_command_line_would(path, body, tmp_path, monkeypatch):
    """The API's options object equals what `canary ...` parses to, key for key."""
    Workspace.create(tmp_path)
    (tmp_path / "tests").mkdir()
    monkeypatch.chdir(tmp_path)
    endpoint = next(e for e in WORK if e.path == path)
    command = _command(path).split("::")
    request = endpoint.model.model_validate(body)
    cli = parser().parse_args(command_line(request, *command))
    canary.config.pluginmanager.hook.canary_cmdline_modifyargs(parser=parser(), args=cli)
    api = options_for(request, *command)
    assert vars(api) == vars(cli)


def test_denied_dests_are_refused():
    from pydantic import BaseModel

    class Wipe(BaseModel):
        wipe: typing.Annotated[bool, Dest("wipe_workspace")] = True

    with pytest.raises(ValueError, match="denied"):
        to_options(Wipe(), parser().get_subparser("run"), defaults(parser(), "run"))
