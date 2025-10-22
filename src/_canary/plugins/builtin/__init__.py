# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from . import addoption
from . import discover
from . import email
from . import html
from . import json
from . import junit
from . import markdown
from . import mask
from . import post_clean
from . import pyt
from . import repeat
from . import reporting
from . import rpool
from . import runtest_protocol
from . import testcase_generator
from .executor import TestCaseExecutor

plugins = [
    addoption,
    TestCaseExecutor(),
    discover,
    email,
    html,
    json,
    junit,
    markdown,
    mask,
    post_clean,
    pyt,
    repeat,
    reporting,
    rpool,
    runtest_protocol,
    testcase_generator,
]
