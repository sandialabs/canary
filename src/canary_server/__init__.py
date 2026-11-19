# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""canary_server: a workspace's file-based command server.

``canary server start`` runs a server for the current workspace in the foreground (use
``nohup canary server start &`` to keep one running after the terminal closes); its state lives in
``.canary/var/server/`` (see :mod:`canary_server.server`).  ``canary --server run ...``
(or ``exec``, ``collect``, ``select``, ``hpc run``) sends the command to it instead of
running it here, and
``canary server post JSON`` does the same for a request given as data (see
:mod:`canary_server.requests`).  Requests run one at a time, each in its own ``canary``
child process.
"""

import argparse
import json
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
        sub.add_parser(
            "start", help="Run the server for this workspace (blocks; background it with the shell)"
        )
        sub.add_parser("stop", help="Stop the server (interrupts the running request)")
        p = sub.add_parser("status", help="Show the server, its running request, and the queue")
        p.add_argument("--json", action="store_true", help="Emit JSON")
        p = sub.add_parser("post", help="Submit a request given as JSON; print its id")
        p.add_argument(
            "request", help='JSON such as \'{"command": "run", "args": ["tests"]}\', or - for stdin'
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
        from _canary.workspace.workspace import Workspace

        root = Workspace.load().root
        match args.server_cmd:
            case "start":
                server.Server(root).run()
                return 0
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
    data = json.loads(sys.stdin.read() if text == "-" else text)
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


@canary.hookimpl
def canary_addoption(parser: "canary.Parser") -> None:
    parser.add_argument(
        "--server",
        action="store_true",
        default=False,
        group="canary server",
        help="Run the command (run, exec, collect, select, hpc run) on this workspace's server",
    )


@canary.hookimpl
def canary_invoke_command(command, args: argparse.Namespace, argv: list[str]) -> int | None:
    """With ``--server``, send the command to the workspace's server and follow it."""
    if not getattr(args, "server", False):
        return None
    from _canary.workspace.workspace import Workspace

    options, command_args = requests.split_command_line(argv, command.name)
    if not requests.server_runs(command.name, command_args):
        shown = " ".join([command.name, *command_args[:1]])
        raise ValueError(
            f"--server: the server runs {requests.server_commands()}; "
            f"run 'canary {shown}' without --server"
        )
    root = Workspace.load().root
    _require_server(root)
    request_id = requests.submit(root, requests.make_request(command.name, command_args, options))
    return requests.follow(root, request_id)


@canary.hookimpl
def canary_cmdline_modifyargs(parser: "canary.Parser", args: argparse.Namespace) -> None:
    """Refuse ``canary rm`` and ``canary run -w`` on a workspace a live server owns."""
    import os

    from _canary.workspace.locator import workspace_at

    command = getattr(args, "command", None)
    if command == "rm":
        path = getattr(args, "rm_path", None) or os.getcwd()
    elif command == "run" and getattr(args, "wipe_workspace", False):
        if getattr(args, "server", False):
            raise ValueError(
                "canary run -w cannot go through the server: it would remove the server's workspace"
            )
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
