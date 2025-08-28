# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

from _canary.config import Config


def test_issue_78():
    with open(os.path.join(os.path.dirname(__file__), "config.json"), "r") as fh:
        conf = Config()
        conf.load_snapshot(fh)

    rp = conf.resource_pool

    # these asserts pass
    assert rp.pinfo("cpus_per_node") != 0
    assert rp.pinfo("gpus_per_node") != 0

    # these asserts fail
    assert rp.pinfo("gpu_count") != 0
    assert rp.pinfo("cpu_count") != 0
