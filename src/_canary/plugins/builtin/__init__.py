# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from . import discover
from . import email
from . import gitlab
from . import html
from . import json
from . import junit
from . import markdown
from . import mask
from . import oversubscribe
from . import post_clean
from . import pyt
from . import repeat
from . import reporting
from . import resource
from . import runtest_protocol
from . import runtests
from . import testcase_generator

plugins = [
    discover,
    email,
    gitlab,
    html,
    json,
    junit,
    markdown,
    mask,
    oversubscribe,
    post_clean,
    pyt,
    repeat,
    reporting,
    resource,
    runtest_protocol,
    runtests,
    testcase_generator,
]
