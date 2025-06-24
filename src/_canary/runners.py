# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import abc
import os
from typing import Any

from . import config
from .test.atc import AbstractTestCase
from .test.batch import TestBatch
from .test.case import TestCase


class AbstractTestRunner:
    """Abstract class for running ``AbstractTestCase``.  This class exists for two reasons:

    1. To provide a __call__ method to ``ProcessPoolExuctor.submit``
    2. To provide a mechanism for a TestBatch to call back to canary to run the the cases in it

    """

    scheduled = False

    def __call__(self, case: AbstractTestCase, *args: str, **kwargs: Any) -> None:
        config.null()  # Make sure config is loaded, since this may be called in a new subprocess
        self.run(case, **kwargs)
        return None

    @abc.abstractmethod
    def run(self, obj: AbstractTestCase, **kwargs: Any) -> None: ...


class TestCaseRunner(AbstractTestRunner):
    """The default runner for running a single :class:`~TestCase`"""

    def run(self, obj: "AbstractTestCase", **kwargs: Any) -> None:
        assert isinstance(obj, TestCase)
        try:
            config.plugin_manager.hook.canary_testcase_setup(case=obj)
            config.plugin_manager.hook.canary_testcase_run(
                case=obj, qsize=kwargs.get("qsize", 1), qrank=kwargs.get("qrank", 1)
            )
        finally:
            config.plugin_manager.hook.canary_testcase_finish(case=obj)


class BatchRunner(AbstractTestRunner):
    """Run a batch of test cases

    The batch runner works by calling canary on itself and requesting the tests in the batch are
    run as exclusive test cases.

    """

    def __init__(self) -> None:
        super().__init__()

        # by this point, hpc_connect should have already be set up
        assert config.backend is not None

    def run(self, obj: AbstractTestCase, **kwargs: Any) -> None:
        assert isinstance(obj, TestBatch)
        try:
            config.plugin_manager.hook.canary_testbatch_setup(batch=obj)
            config.plugin_manager.hook.canary_testbatch_run(
                batch=obj, qsize=kwargs.get("qsize", 1), qrank=kwargs.get("qrank", 1)
            )
        finally:
            config.plugin_manager.hook.canary_testbatch_finish(batch=obj)


def factory() -> "AbstractTestRunner":
    runner: "AbstractTestRunner"
    if config.backend is None:
        runner = TestCaseRunner()
    else:
        runner = BatchRunner()
        if nodes_per_batch := os.getenv("CANARY_NODES_PER_BATCH"):
            sys_node_count = config.resource_pool.pinfo("node_count")
            if int(nodes_per_batch) > config.resource_pool.pinfo("node_count"):
                raise ValueError(
                    f"CANARY_NODES_PER_BATCH={nodes_per_batch} exceeds "
                    f"node count of system ({sys_node_count})"
                )
    return runner
