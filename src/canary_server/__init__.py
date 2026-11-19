# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""canary_server: a workspace's file-based command server.

``canary server start`` runs a server for the current workspace in the foreground (use
``nohup canary server start &`` to keep one running after the terminal closes); its state lives in
``.canary/var/server/`` (see :mod:`canary_server.server`).  ``canary --connect=WHERE run ...``
(or ``exec``, ``collect``, ``select``, ``hpc run``) sends the command to it instead of
running it here, and
``canary server post JSON`` does the same for a request given as data (see
:mod:`canary_server.requests`).  Requests run one at a time, each in its own ``canary``
child process.
"""

import argparse
import json
import os
import sys

import canary

from . import requests
from . import server

logger = canary.get_logger(__name__)


class ServerCommand(canary.CanarySubcommand):
    name = "server"
    description = "Run and manage this workspace's command server"

    def setup_parser(self, parser: "canary.Parser") -> None:
        sub = parser.add_subparsers(dest="server_cmd", metavar="", title="subcommands")
        p = sub.add_parser(
            "start", help="Run the server for this workspace (blocks; background it with the shell)"
        )
        p.add_argument(
            "-w",
            dest="wipe",
            action="store_true",
            help="Remove the workspace here (if any) and start with a fresh one",
        )
        sub.add_parser("stop", help="Stop the server (interrupts the running request)")
        p = sub.add_parser("status", help="Show the server, its running request, and the queue")
        p.add_argument("--json", action="store_true", help="Emit JSON")
        p = sub.add_parser("post", help="Submit a request given as JSON; print its id")
        p.add_argument(
            "request",
            help=(
                'the request: JSON such as \'{"command": "run", "args": ["tests"]}\', '
                "a file holding it, or - to read stdin"
            ),
        )
        p.add_argument("--wait", action="store_true", help="Follow the request until it finishes")
        p = sub.add_parser("get", help="Show a request's record as JSON")
        p.add_argument("id", help="Request id")
        p.add_argument("--output", action="store_true", help="Print the request's output instead")
        p = sub.add_parser("wait", help="Follow a request until it finishes; exit with its code")
        p.add_argument("id", help="Request id")
        p.add_argument("--quiet", action="store_true", help="Do not print the request's output")
        p = sub.add_parser("cancel", help="Cancel a queued or running request")
        p.add_argument("id", help="Request id")

    def execute(self, args: argparse.Namespace) -> int:
        if args.server_cmd == "start":
            server.Server(_start_root(args)).run()
            return 0
        root = workspace_root(args)
        match args.server_cmd:
            case "stop":
                if server.stop(root):
                    logger.info("[bold]Stopped[/] canary server")
                else:
                    logger.info("No canary server is running for this workspace")
                return 0
            case "status":
                return _status(root, as_json=args.json)
            case "post":
                return _post(root, args.request, wait=args.wait)
            case "get":
                record = requests.get(root, args.id)  # nosec B113 (canary_server.requests, not the HTTP library)
                if args.output:
                    for name, stream in (("stdout", sys.stdout), ("stderr", sys.stderr)):
                        path = requests.request_dir(root, args.id) / name
                        if path.exists():
                            stream.write(path.read_text(errors="replace"))
                else:
                    print(json.dumps(record, indent=2))
                return 0
            case "wait":
                return requests.follow(root, args.id, quiet=args.quiet)
            case "cancel":
                print(json.dumps({"id": args.id, "state": requests.cancel(root, args.id)}))
                return 0
        raise ValueError("canary server: expected start, stop, status, post, get, wait or cancel")


def _status(root, *, as_json: bool) -> int:
    info = server.read_info(root)
    alive = info is not None and info.is_alive()
    running = requests.running_id(root)
    queued = requests.queued_ids(root)
    if as_json:
        record = info.to_dict() if info is not None else {"alive": False}
        print(json.dumps({**record, "running": running, "queued": queued}))
    elif alive:
        assert info is not None
        print(f"running: pid {info.pid} on {info.host}, version {info.version}")
        print(f"request: {running or 'none'}; queued: {len(queued)}")
        for position, request_id in enumerate(queued, start=1):
            print(f"  {position}. {request_id}")
    else:
        print("not running" + (f" ({len(queued)} queued)" if queued else ""))
    return 0 if alive else 1


def _post(root, text: str, *, wait: bool) -> int:
    data = json.loads(_request_text(text))
    if not isinstance(data, dict) or "command" not in data:
        raise ValueError('a request is a JSON object with "command" (and usually "args")')
    _require_server(root)
    request = requests.make_request(
        data["command"],
        data.get("args", []),
        data.get("options", []),
        cwd=data.get("cwd"),
        env=data.get("env"),
    )
    request_id = requests.submit(root, request)
    print(json.dumps({"id": request_id}))
    sys.stdout.flush()
    return requests.follow(root, request_id) if wait else 0


def _request_text(text: str) -> str:
    """The request JSON: *text* itself if it starts with ``{``, stdin for ``-``, else a file.

    (``@FILE`` is not used: canary's parser already expands ``@FILE`` into arguments.)
    """
    if text.lstrip().startswith("{"):
        return text
    if text == "-":
        return sys.stdin.read()
    try:
        with open(text) as fh:
            return fh.read()
    except OSError as exc:
        raise ValueError(f"canary server post: cannot read {text}: {exc.strerror}") from None


def _require_server(root) -> None:
    info = server.read_info(root)
    if info is None or not info.is_alive():
        raise RuntimeError(
            "no canary server is running for this workspace; start one with 'canary server start'"
        )


@canary.hookimpl
def canary_addcommand(parser: "canary.Parser") -> None:
    parser.add_command(ServerCommand())


@canary.hookimpl
def canary_capabilities() -> dict | None:
    from _canary.util.query_data import load_query_data

    return load_query_data("canary_server.data", "capabilities.json")


@canary.hookimpl
def canary_skills() -> dict | None:
    from _canary.util.query_data import load_query_data

    return load_query_data("canary_server.data", "skills.json")


def workspace_root(args: argparse.Namespace):
    """The workspace whose server to use: found from ``--connect WHERE``, else from here.

    WHERE is a path (or ``file://`` URL) inside or above a workspace; it is the start of
    the usual upward workspace search, so ``--connect=.`` works anywhere in the tree.
    """
    from _canary.workspace.workspace import Workspace

    where = _where(args)
    return Workspace.load(start=where).root if where is not None else Workspace.load().root


def _where(args: argparse.Namespace) -> str | None:
    """``--connect``'s WHERE as a path (``file://`` stripped), or ``None``."""
    where = getattr(args, "connect", None)
    if where is None:
        return None
    if where.startswith("file://"):
        return where[len("file://") :] or "/"
    if "://" in where:
        raise ValueError(f"--connect {where}: only file:// (or a plain path) is supported")
    return where


def _start_root(args: argparse.Namespace):
    """The workspace ``server start`` serves, created (or, with ``-w``, recreated) if needed.

    Like ``canary run``: the workspace found from here is used, or one is created here;
    ``-w`` removes only the workspace located exactly here (never an enclosing one) and
    creates a fresh one -- but never one a live server owns.
    """
    from _canary.workspace.workspace import NotAWorkspaceError
    from _canary.workspace.workspace import Workspace

    where = _where(args) or os.getcwd()
    if getattr(args, "wipe", False):
        existing = Workspace.workspace_at(where)
        if existing is None and (anchor := Workspace.find_anchor(start=where)) is not None:
            raise ValueError(
                f"-w: {where} is inside the workspace at {anchor}, which will not be wiped "
                f"implicitly.  Run from {anchor} or use 'canary rm {anchor}' first."
            )
        if existing is not None:
            info = server.read_info(existing)
            if info is not None and info.is_alive():
                raise server.ServerRunningError(
                    f"a server is already running for this workspace (pid {info.pid} on "
                    f"{info.host}); stop it first with 'canary server stop'"
                )
        Workspace.detach(where)
        return Workspace.create(path=where).root
    try:
        return Workspace.load(start=where).root
    except NotAWorkspaceError:
        logger.info(f"[bold]Creating[/] a canary workspace in {os.path.abspath(where)}")
        return Workspace.create(path=where).root


@canary.hookimpl
def canary_addoption(parser: "canary.Parser") -> None:
    parser.add_argument(
        "--connect",
        dest="connect",
        metavar="WHERE",
        default=None,
        group="canary server",
        help=(
            "Queue the command (run, exec, collect, select, hpc run) on the server of the "
            "workspace found from WHERE (a path or file:// URL; '.' for here) and return"
        ),
    )


@canary.hookimpl(tryfirst=True)
def canary_cmdline_parse(parser: "canary.Parser", args: list[str]) -> argparse.Namespace | None:
    """With ``--connect``, parse only the global options; the server parses the command's.

    The command's arguments are interpreted on the server, in its workspace: parsing them
    here (e.g. classifying a job id against a local workspace that may not exist) would be
    wrong.  ``canary --connect=WHERE server ...`` is parsed normally (it runs here).
    """
    index = _command_index(parser, args)
    if index is None or args[index] == ServerCommand.name:
        return None
    if not any(a == "--connect" or a.startswith("--connect=") for a in args[:index]):
        return None
    if any(a in ("-h", "--help") for a in args[index + 1 :]):
        return None  # help is printed here
    # Parse the global options with a placeholder command that takes no arguments.
    ns = parser.parse_args([*args[:index], "info"])
    ns.command = args[index]
    ns.connect_args = list(args[index + 1 :])
    return ns


def _command_index(parser: "canary.Parser", args: list[str]) -> int | None:
    """Index of the subcommand in *args*, skipping global options and their values."""
    actions = parser._option_string_actions
    i = 0
    while i < len(args):
        token = args[i]
        if not token.startswith("-") or token == "-":
            return i if parser.get_command(token) is not None else None
        name, has_value = token.split("=", 1)[0], "=" in token
        action = actions.get(name)
        takes_value = action is not None and action.nargs != 0 and not has_value
        short_attached = not token.startswith("--") and len(token) > 2  # e.g. -C/x, -pmod
        i += 2 if takes_value and not short_attached else 1
    return None


@canary.hookimpl
def canary_invoke_command(command, args: argparse.Namespace, argv: list[str]) -> int | None:
    """With ``--connect``, queue the command on the workspace's server and return.

    The server prints the command's output on its own terminal (and keeps it in the
    request directory); ``canary server wait ID`` follows it from here.
    """
    if getattr(args, "connect", None) is None or command.name == ServerCommand.name:
        return None  # `canary --connect=WHERE server ...` acts on that server directly
    options, command_args = requests.split_command_line(argv, command.name)
    if not requests.server_runs(command.name, command_args):
        shown = " ".join([command.name, *command_args[:1]])
        raise ValueError(
            f"--connect: the server runs {requests.server_commands()}; "
            f"run 'canary {shown}' without --connect"
        )
    root = workspace_root(args)
    _require_server(root)
    cwd = requests.relative_cwd(requests.client_cwd(), requests.anchor_of(root))
    request = requests.make_request(command.name, command_args, options, cwd=cwd)
    request_id = requests.submit(root, request)
    queue = requests.queued_ids(root)
    position = queue.index(request_id) + 1 if request_id in queue else None
    print(f"canary: request {request_id} queued on the server (position {position})")
    print(f"  follow: canary server wait {request_id}")
    print(f"  cancel: canary server cancel {request_id}")
    return 0


@canary.hookimpl
def canary_cmdline_modifyargs(parser: "canary.Parser", args: argparse.Namespace) -> None:
    """Refuse ``canary rm`` and ``canary run -w`` on a workspace a live server owns."""
    from _canary.workspace.locator import workspace_at

    command = getattr(args, "command", None)
    if getattr(args, "connect", None) is not None and command != ServerCommand.name:
        args.banner = False  # the command runs on the server; this process only queues it
    if command == "rm":
        path = getattr(args, "rm_path", None) or os.getcwd()
    elif command == "run" and getattr(args, "connect", None) is not None:
        if "-w" in getattr(args, "connect_args", []):
            raise ValueError(
                "canary run -w cannot go through the server: it would remove the server's workspace"
            )
        return
    elif command == "run" and getattr(args, "wipe_workspace", False):
        path = getattr(args, "work_tree", None) or os.getcwd()
    else:
        return
    root = workspace_at(path)
    info = server.read_info(root) if root is not None else None
    if info is not None and info.is_alive():
        action = "remove" if command == "rm" else "wipe"
        raise ValueError(
            f"cannot {action} the workspace at {root}: a canary server is running for it "
            f"(pid {info.pid} on {info.host}); stop it first with 'canary server stop'"
        )
