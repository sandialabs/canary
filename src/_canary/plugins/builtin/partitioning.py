import math
from typing import TYPE_CHECKING

from ... import config
from ...util import logging
from ...util import partitioning
from ..hookspec import hookimpl

if TYPE_CHECKING:
    from ...config import Config
    from ...test.batch import TestBatch
    from ...test.case import TestCase


@hookimpl(specname="canary_testcases_batch")
def partition_by_count(cases: list["TestCase"]) -> list["TestBatch"] | None:
    batchopts = config.getoption("batch", {})
    if scheme := batchopts.get("scheme"):
        if scheme == "count":
            logging.info("Batching test cases using scheme=count")
            count: int = math.ceil(batchopts["count"])
            return partitioning.partition_n(cases, n=count)
    return None


@hookimpl(specname="canary_testcases_batch")
def partition_consistent(cases: list["TestCase"]) -> list["TestBatch"] | None:
    batchopts = config.getoption("batch", {})
    if scheme := batchopts.get("scheme"):
        if scheme == "isolate":
            logging.info("Batching test cases using scheme=isolate")
            return partitioning.partition_x(cases)
    return None


@hookimpl(specname="canary_testcases_batch", trylast=True)
def partition_by_time(cases: list["TestCase"]) -> list["TestBatch"] | None:
    batchopts = config.getoption("batch", {})
    scheme = batchopts.get("scheme")
    if scheme in ("duration", None):
        logging.info("Batching test cases using scheme=duration")
        default_length = 30 * 60
        length = float(batchopts.get("duration") or default_length)  # 30 minute default
        return partitioning.autopartition(cases, t=length)
    return None


@hookimpl
def canary_configure(config: "Config") -> None:
    """Do some post configuration checks"""
    batchopts = config.getoption("batch")
    if batchopts:
        if config.scheduler is None:
            raise ValueError("Test batching requires a batch:scheduler")
        if scheme := batchopts.get("scheme"):
            if scheme == "count":
                if (count := batchopts.get("count")) is None:
                    raise ValueError("batch:scheme=count requires batch:count=N be defined")
                if count <= 0:
                    raise ValueError(f"batch:count={count} must be > 0")
