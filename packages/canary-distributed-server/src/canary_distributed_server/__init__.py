import argparse
import getpass
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import uvicorn
import yaml

from . import app


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(title="subcommands", dest="subcommand")

    def get_subparser(
        *, name: str, help: str, needs_server_url: bool = True
    ) -> argparse.ArgumentParser:
        nonlocal subparsers
        p = subparsers.add_parser(name, help=help)
        if needs_server_url:
            p.add_argument(
                "--server-url",
                metavar="URL",
                dest="server_url",
                default=os.getenv("CANARY_DISTRIBUTED_URL"),
                help="URL to resource pool server [default: %(default)s]",
            )
        return p

    p = get_subparser(name=StartServer.name, help=StartServer.description, needs_server_url=False)
    StartServer.setup_parser(p)

    p = get_subparser(name=AddHost.name, help=AddHost.description)
    AddHost.setup_parser(p)

    p = get_subparser(name=RemoveHost.name, help=RemoveHost.description)
    RemoveHost.setup_parser(p)

    p = get_subparser(name=Status.name, help=Status.description)
    Status.setup_parser(p)

    p = get_subparser(name=TakeOffline.name, help=TakeOffline.description)
    TakeOffline.setup_parser(p)

    p = get_subparser(name=BringOnline.name, help=BringOnline.description)
    BringOnline.setup_parser(p)

    p = get_subparser(name=RestoreAllSlots.name, help=RestoreAllSlots.description)
    RestoreAllSlots.setup_parser(p)

    p = get_subparser(name=RX.name, help=RX.description)
    RX.setup_parser(p)

    args = parser.parse_args()
    command: Command
    if args.subcommand == StartServer.name:
        command = StartServer(args)
    elif args.subcommand == AddHost.name:
        command = AddHost(args)
    elif args.subcommand == RemoveHost.name:
        command = RemoveHost(args)
    elif args.subcommand == Status.name:
        command = Status(args)
    elif args.subcommand == RestoreAllSlots.name:
        command = RestoreAllSlots(args)
    elif args.subcommand == RX.name:
        command = RX(args)
    elif args.subcommand == TakeOffline.name:
        command = TakeOffline(args)
    elif args.subcommand == BringOnline.name:
        command = BringOnline(args)
    else:
        raise ValueError(f"Unknown command {args.subcommand}")
    return command(args)


class Command:
    name = None
    description = None
    endpoint = None

    def __init__(self, args: argparse.Namespace) -> None:
        base_url = args.server_url
        if base_url is None:
            raise ValueError("Missing required argument: --server-url or CANARY_DISTRIBUTED_URL")
        if "://" not in base_url:
            base_url = f"http://{base_url}"
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def setup_parser(parser: argparse.ArgumentParser) -> None:
        pass

    def curl(
        self, method: str = "POST", data: dict[str, Any] | None = None, **parameters: str
    ) -> subprocess.CompletedProcess:
        args = ["curl", "-g", "--fail-with-body"]
        args.extend(["-X", method])
        args.extend(["-H", f"X-User: {getpass.getuser()}"])
        args.extend(["-H", f"X-Host: {os.uname().nodename}"])
        if data:
            args.extend(["-H", "Content-Type: application/json"])
            payload = json.dumps(data, separators=(",", ":"), indent=None)
            args.extend(["-d", payload])
        url = f"{self.base_url}{self.endpoint}"
        if parameters:
            querystrings = urlencode(parameters)
            url += f"?{querystrings}"
        args.append(url)
        return subprocess.run(args, capture_output=True, text=True)

    def __call__(self, args: argparse.Namespace) -> int:
        raise NotImplementedError


class StartServer(Command):
    name = "start"
    description = "Start Canary distributed resource pool server"
    endpoint = None

    def __init__(self, args: argparse.Namespace) -> None:
        self.state_dir: Path = Path(args.state_dir or tempfile.gettempdir()).absolute()
        self.host: str = args.host
        self.port: int = args.port
        self.ssl_certfile: str | None = args.ssl_certfile
        self.ssl_keyfile: str | None = args.ssl_keyfile

    @staticmethod
    def setup_parser(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--state-dir",
            metavar="DIRNAME",
            dest="state_dir",
            help="Path to resource pool server state directory [default: %(default)s]",
        )
        parser.add_argument(
            "--host", default="0.0.0.0", help="Interface to bind [default: %(default)s]"
        )
        parser.add_argument(
            "--port", type=int, default=8000, help="Port to bind [default: %(default)s]"
        )
        parser.add_argument("--ssl-certfile", help="TLS certificate file")
        parser.add_argument("--ssl-keyfile", help="TLS private key file")

    @property
    def meta(self) -> argparse.Namespace:
        raise NotImplementedError

    def __call__(self, args: argparse.Namespace) -> int:
        self.state_dir.mkdir(parents=True, exist_ok=True)

        fastapi_app = app.make_fastapi(self.state_dir)

        kwargs: dict[str, Any] = {"host": self.host, "port": self.port, "workers": 1}

        if self.ssl_certfile or self.ssl_keyfile:
            if not self.ssl_certfile or not self.ssl_keyfile:
                raise ValueError("Both --ssl-certfile and --ssl-keyfile are required for HTTPS")
            kwargs["ssl_certfile"] = self.ssl_certfile
            kwargs["ssl_keyfile"] = self.ssl_keyfile

        print("Serving Canary distributed resource pool")
        print(f"Listening on {self.host}:{self.port}")

        uvicorn.run(fastapi_app, **kwargs)
        return 0


class AddHost(Command):
    name = "add-host"
    description = "Add a host to the distributed resource pool"
    endpoint = "/add_host"

    @staticmethod
    def setup_parser(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--tags",
            dest="canary_distributed_tags",
            metavar="TAGS",
            type=lambda arg: [_.strip() for _ in arg.split(",") if _.strip()],
            help="Comma separated list of tags",
        )
        parser.add_argument(
            "--groups",
            dest="canary_distributed_groups",
            metavar="GROUPS",
            type=lambda arg: [_.strip() for _ in arg.split(",") if _.strip()],
            help="Comma separated list of groups that can access this machine",
        )
        parser.add_argument(
            "--host",
            required=True,
            dest="canary_distributed_host",
            metavar="HOST",
            help="Add resources for HOST",
        )
        parser.add_argument(
            "canary_distributed_resources",
            metavar="TYPE=N [TYPE=N ...]",
            nargs=argparse.REMAINDER,
            type=resource_splitter,
            help="Count of resources of type TYPE on HOST",
        )

    def __call__(self, args: argparse.Namespace) -> int:
        hostname = args.canary_distributed_host
        resources = args.canary_distributed_resources
        if not resources:
            raise ValueError("No resources specified.  Provide resources explicitly, e.g. cpus=8")
        data = {"hostname": hostname, "resources": resources, "state": "online"}
        if tags := args.canary_distributed_tags:
            data["tags"] = tags
        if groups := args.canary_distributed_groups:
            data["groups"] = groups
        p = self.curl(data=data)
        if p.returncode != 0:
            if p.stdout:
                print(p.stdout)
            if p.stderr:
                print(p.stderr, file=sys.stderr)
        else:
            print(p.stdout)
        return p.returncode


class BringOnline(Command):
    name = "bring-online"
    description = "Bring HOST online"
    endpoint = "/bring_online"

    @staticmethod
    def setup_parser(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--host",
            required=True,
            dest="canary_distributed_host",
            metavar="HOST",
            help="Bring HOST online",
        )

    def __call__(self, args: argparse.Namespace) -> int:
        p = self.curl(hostname=args.canary_distributed_host)
        if p.returncode != 0:
            print(p.stderr)
        print(p.stdout)
        return p.returncode


class TakeOffline(Command):
    name = "take-offline"
    description = "Take HOST off line"
    endpoint = "/take_offline"

    @staticmethod
    def setup_parser(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--host",
            required=True,
            dest="canary_distributed_host",
            metavar="HOST",
            help="Add resources for HOST [default: %(default)s]",
        )

    def __call__(self, args: argparse.Namespace) -> int:
        p = self.curl(hostname=args.canary_distributed_host)
        if p.returncode != 0:
            print(p.stderr)
        print(p.stdout)
        return p.returncode


class RemoveHost(Command):
    name = "remove-host"
    description = "Remove host from distributed pool"
    endpoint = "/remove_host"

    @staticmethod
    def setup_parser(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--host",
            required=True,
            dest="canary_distributed_host",
            metavar="HOST",
            help="Add resources for HOST",
        )

    def __call__(self, args: argparse.Namespace) -> int:
        p = self.curl(hostname=args.canary_distributed_host)
        if p.returncode != 0:
            print(p.stderr)
        print(p.stdout)
        return p.returncode


class Status(Command):
    name = "status"
    description = "Check status of server"
    endpoint = "/status"

    def __call__(self, args: argparse.Namespace) -> int:
        p = self.curl(method="GET")
        if p.returncode != 0:
            print(p.stderr)
        else:
            data = json.loads(p.stdout)
            yaml.dump(data, sys.stdout, default_flow_style=False)
        return p.returncode


class RestoreAllSlots(Command):
    name = "restore-slots"
    description = "Restore all slots to original values"
    endpoint = "/restore_slots"

    def __call__(self, args: argparse.Namespace) -> int:
        p = self.curl()
        if p.returncode != 0:
            print(p.stderr)
        print(p.stdout)
        return p.returncode


class RX(Command):
    name = "rx"
    description = "Check in expired check outs"
    endpoint = "/rx"

    def __call__(self, args: argparse.Namespace) -> int:
        p = self.curl()
        if p.returncode != 0:
            print(p.stderr)
        print(p.stdout)
        return p.returncode


def resource_splitter(arg: str) -> dict[str, Any]:
    type_, count_str = re.split(r"[=:]", arg, maxsplit=1)
    count = int(count_str)
    if count <= 0:
        raise argparse.ArgumentTypeError(f"Resource count must be positive: {arg}")
    return {"type": type_, "count": count}
