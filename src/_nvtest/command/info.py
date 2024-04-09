import argparse
import json

from .. import config
from ..config.argparsing import Parser
from ..session import Session
from ..util import tty

description = "Print information about a test session"


def setup_parser(parser: Parser):
    pass


def info(args: argparse.Namespace) -> int:
    work_tree = config.get("session:work_tree")
    if work_tree is None:
        tty.die("not a nvtest session (or any of the parent directories): .nvtest")
    session = Session.load(mode="r")
    p = config.get("system:os:name")
    v = config.get("python:version")
    tty.print(f"{p} -- Python {v}")
    tty.print(f"Available cpus: {session.avail_cpus}")
    tty.print(f"Available cpus per test: {session.avail_cpus_per_test}")
    if session.avail_devices:
        tty.print(f"Available devices: {session.avail_devices}")
        tty.print(f"Available devices per test: {session.avail_devices_per_test}")
    tty.print(f"Maximum number of asynchronous jobs: {session.avail_workers}")
    tty.print(f"Working tree: {session.work_tree}")
    tty.print("Initialization options:")
    for key, var in session.ini_options.items():
        tty.print(f"  {key}: {json.dumps(var)}")
    return 0
