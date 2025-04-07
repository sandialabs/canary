#!/usr/bin/env python3
# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import os

assert os.environ["CTEST_RESOURCE_GROUP_COUNT"] == "1"
assert os.environ["CTEST_RESOURCE_GROUP_0"] == "gpus"
assert "CTEST_RESOURCE_GROUP_0_GPUS" in os.environ
print("TEST CERTAINLY PASSED!")
