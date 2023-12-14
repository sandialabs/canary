from typing import Optional
from typing import Union

from ..test.partition import Partition
from ..test.testcase import TestCase
from ..third_party import rprobe
from ..util import tty
from .base import Queue
from .batch import BatchQueue
from .direct import DirectQueue


def factory(
    items: Union[list[TestCase], list[Partition]],
    workers: int = 5,
    cpu_count: Optional[int] = None,
    device_count: Optional[int] = None,
) -> Queue:
    tty.verbose("Setting up a test case queue")
    cpus: int = cpu_count or rprobe.cpu_count()
    if not isinstance(items, list):
        raise ValueError("Expected list of items to queue")
    elif isinstance(items, list) and isinstance(items[0], TestCase):
        tty.verbose(f"Queue type = {DirectQueue.__name__}")
        return DirectQueue(cpus, workers, items)  # type: ignore
    elif isinstance(items, list) and isinstance(items[0], Partition):
        tty.verbose(f"Queue type = {BatchQueue.__name__}")
        return BatchQueue(cpus, workers, items)  # type: ignore
    raise ValueError(f"unknown queue for items of type {items[0].__class__.__name__}")
