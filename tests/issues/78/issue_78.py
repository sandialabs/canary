# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

from _canary.config import Config


def test_issue_78():
    with open(os.path.join(os.path.dirname(__file__), "config.json"), "r") as fh:
        conf = Config()
        conf.load_snapshot(fh)
