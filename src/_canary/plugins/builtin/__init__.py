# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from . import addoption
from . import collect
from . import email
from . import generate
from . import html
from . import json
from . import junit
from . import markdown
from . import post_clean
from . import pyt
from . import repeat
from . import reporting
from . import rpool
from . import runtest_protocol
from . import select
from . import testcase_generator
from .executor import TestCaseExecutor

plugins = [
    addoption,
    TestCaseExecutor(),
    collect.Collector(),
    collect,
    email,
    generate,
    html,
    json,
    junit,
    markdown,
    post_clean,
    pyt,
    repeat,
    reporting,
    rpool,
    runtest_protocol,
    select,
    testcase_generator,
]
