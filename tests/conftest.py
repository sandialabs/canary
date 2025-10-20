# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

import pytest

import _canary.config


def pytest_addoption(parser):
    parser.addoption("--cpus-per-node", action="store", help="Number of CPUs per node")
    parser.addoption("--gpus-per-node", action="store", help="Number of CPUs per node")


@pytest.fixture(scope="function", autouse=True)
def config(request):
    try:
        env_copy = os.environ.copy()
        os.environ.pop("CANARYCFG64", None)
        os.environ["CANARY_DISABLE_KB"] = "1"
        if opt := request.config.getoption("--cpus-per-node"):
            cpus = int(opt)
            os.environ["_CANARY_TESTING_CPUS"] = str(cpus)
        else:
            cpus = 8
        if opt := request.config.getoption("--gpus-per-node"):
            gpus = int(opt)
            os.environ["_CANARY_TESTING_GPUS"] = str(gpus)
        else:
            gpus = 0
        _canary.config._config = _canary.config.config.Config()
        yield
    except:
        os.environ.clear()
        os.environ.update(env_copy)
