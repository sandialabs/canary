# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os

from _canary.config import Config


def test_legacy_config():
    cfg = Config()
    file = os.path.join(os.path.dirname(__file__), "data/legacy_config.json")
    with open(file) as fh:
        cfg.load_snapshot(fh)
    fullversion = cfg.get("system:os:fullversion")
    assert (
        fullversion
        == "Linux manzano-login11 4.18.0-553.53.1.1toss.t4.x86_64 #1 SMP Wed May 21 12:12:01 PDT 2025 x86_64 x86_64"
    )
