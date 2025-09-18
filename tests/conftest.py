# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

import pytest

import _canary.config


def pytest_addoption(parser):
    parser.addoption("--cpus-per-node", action="store", default="8", help="Number of CPUs per node")


@pytest.fixture(scope="function", autouse=True)
def config(request):
    try:
        env_copy = os.environ.copy()
        os.environ.pop("CANARYCFG64", None)
        os.environ["CANARY_DISABLE_KB"] = "1"
        _canary.config._config = _canary.config.config.Config()
        cpus_per_node = int(request.config.getoption("--cpus-per-node"))
        _canary.config.resource_pool.populate(cpus=cpus_per_node, gpus=0)
        yield
    except:
        os.environ.clear()
        os.environ.update(env_copy)
