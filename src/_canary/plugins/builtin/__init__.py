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
from . import oversubscribe
from . import post_clean
from . import pyt
from . import repeat
from . import reporting
from . import runtest_protocol
from . import testcase_generator
from .conductor import Conductor

plugins = [
    addoption,
    discover,
    email,
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
    runtest_protocol,
    testcase_generator,
]


plugin_instances = [Conductor()]
