import argparse
import json

from .. import config
from ..config.argparsing import Parser
from ..session import Session
from ..util import logging

description = "Print information about a test session"


def setup_parser(parser: Parser):
    pass


def info(args: argparse.Namespace) -> int:
    work_tree = config.get("session:work_tree")
    if work_tree is None:
        raise ValueError("not a nvtest session (or any of the parent directories): .nvtest")
    with logging.level(logging.WARNING):
        session = Session.load(mode="r")
    p = config.get("system:os:name")
    v = config.get("python:version")
    logging.emit(f"Platform: {p} -- Python {v}")
    logging.emit(f"Available cpus: {session.avail_cpus}")
    logging.emit(f"Available cpus per test: {session.avail_cpus_per_test}")
    if session.avail_devices:
        logging.emit(f"Available devices: {session.avail_devices}")
        logging.emit(f"Available devices per test: {session.avail_devices_per_test}")
    logging.emit(f"Maximum number of asynchronous jobs: {session.avail_workers}")
    logging.emit(f"Working tree: {session.work_tree}")
    logging.emit("Initialization options:")
    for key, var in session.ini_options.items():
        logging.emit(f"  {key}: {json.dumps(var)}")
    return 0
