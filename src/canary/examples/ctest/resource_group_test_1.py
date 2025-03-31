#!/usr/bin/env python3
# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import os

assert os.environ["CTEST_RESOURCE_GROUP_COUNT"] == "2"
assert os.environ["CTEST_RESOURCE_GROUP_0"] == "gpus"
assert os.environ["CTEST_RESOURCE_GROUP_1"] == "gpus"
assert "CTEST_RESOURCE_GROUP_0_GPUS" in os.environ
assert "CTEST_RESOURCE_GROUP_1_GPUS" in os.environ
print("TEST PASSED!")
