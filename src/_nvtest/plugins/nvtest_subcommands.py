import nvtest

from ..command.config import Config
from ..command.create_batches import CreateBatches
from ..command.describe import Describe
from ..command.find import Find
from ..command.info import Info
from ..command.merge_batches import MergeBatches
from ..command.run_batch import RunBatch
from ..command.run_batched import RunBatched
from ..command.run_case import RunCase
from ..command.run_tests import RunTests
from ..command.setup import Setup
from ..session import Session


@nvtest.plugin.register("config", scope="session", stage="bootstrap")
def config(session: Session):
    session.parser.add_command("config", Config)


@nvtest.plugin.register("describe", scope="session", stage="bootstrap")
def describe(session: Session):
    session.parser.add_command("describe", Describe)


@nvtest.plugin.register("find", scope="session", stage="bootstrap")
def find(session: Session):
    session.parser.add_command("find", Find)


@nvtest.plugin.register("info", scope="session", stage="bootstrap")
def info(session: Session):
    session.parser.add_command("info", Info)


@nvtest.plugin.register("create-batches", scope="session", stage="bootstrap")
def create_batches(session: "Session"):
    session.parser.add_command("create-batches", CreateBatches)


@nvtest.plugin.register("run-batched", scope="session", stage="bootstrap")
def run_batched(session: Session):
    session.parser.add_command("run-batched", RunBatched)


@nvtest.plugin.register("run-batch", scope="session", stage="bootstrap")
def run_batch(session: Session):
    session.parser.add_command("run-batch", RunBatch)


@nvtest.plugin.register("merge-batches", scope="session", stage="bootstrap")
def merge_batches(session: Session):
    session.parser.add_command("merge-batches", MergeBatches)


@nvtest.plugin.register("setup", scope="session", stage="bootstrap")
def setup(session: Session):
    session.parser.add_command("setup", Setup)


@nvtest.plugin.register("run-case", scope="session", stage="bootstrap")
def run_case(session: Session):
    session.parser.add_command("run-case", RunCase)


@nvtest.plugin.register("run-tests", scope="session", stage="bootstrap")
def run_tests(session: Session):
    session.parser.add_command("run-tests", RunTests)
