# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
from .core.job import Dependency  # noqa: F401
from .core.job import Job
from .core.job import load_job_from_file
from .core.job import load_job_from_state

# Legacy/backward compatiblity
TestCase = Job
load_testcase_from_file = load_job_from_file
load_testcase_from_state = load_job_from_state
