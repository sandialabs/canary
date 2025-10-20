import getpass
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from ..plugins.types import Result
from ..testcase import TestCase
from .rpool import ResourceUnavailable


class ResourcePoolAdapter:
    """Adapter to communicate with the pool server via curl + Unix socket."""

    def __init__(self):
        self.sockefile: Path | None = None
        self.host: str | None = None
        self.port: int | None = None
        if var := os.getenv("CANARY_RESOURCE_POOL_ADDR"):
            protocol, _, address = var.partition(":")
            if protocol == "uds":
                self.socketfile = Path(address)
            elif protocol == "tcp":
                self.host, port = address.split(":")
                self.port = int(port)
            else:
                raise ValueError(f"Incorrect CANARY_RESOURCE_POOL_ADDR protocol {protocol!r}")
        else:
            raise RuntimeError("CANARY_RESOURCE_POOL_ADDR is not defined")

    def curl(self, endpoint: str, method: str = "POST", data: dict | None = None):
        cmd = ["curl", "-s", "-w", "\n%{http_code}"]
        baseurl: str
        if self.socketfile is not None:
            cmd.extend(["--unix-socket", str(self.socketfile)])
            baseurl = "http://localhost"
        else:
            assert self.host is not None
            assert self.port is not None
            baseurl = f"http://{self.host}:{self.port}"
        cmd.extend(["-X", method])
        cmd.extend(["-H", f"X-User: {getpass.getuser()}"])
        cmd.extend(["-H", f"X-Host: {os.uname().nodename}"])
        if data is not None:
            cmd.extend(["-H", "Content-Type: application/json", "-d", json.dumps(data)])
        cmd.append(f"{baseurl}{endpoint}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)
        lines = result.stdout.splitlines()
        data = json.loads("\n".join(lines[:-1]))
        data["http_code"] = int(lines[-1])
        return data

    def empty(self) -> bool:
        return False

    def count(self, type: str) -> int:
        response = self.curl("/count", data=type)
        return response["count"]

    @property
    def types(self) -> list[str]:
        response = self.curl("/types", method="GET")
        return response["types"]

    def accommodates(self, case: TestCase) -> Result:
        response = self.curl("/accommodates", data=case.required_resources())
        return Result(response["ok"], reason=response["reason"])

    def checkout(self, request: list[list[dict[str, Any]]]) -> list[dict[str, list[dict]]]:
        response = self.curl("/checkout", data=request)
        if response["http_code"] == 404:
            raise ResourceUnavailable
        else:
            return response["resources"]

    def checkin(self, request: list[dict[str, list[dict]]]):
        return self.curl("/checkin", data=request)
