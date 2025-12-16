# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from . import addoption
from . import capture
from . import email
from . import html
from . import json
from . import junit
from . import markdown
from . import post_clean
from . import pyt
from . import repeat
from . import testcase_generator

plugins = [
    addoption,
    capture,
    email,
    html,
    json,
    junit,
    markdown,
    post_clean,
    pyt,
    repeat,
    testcase_generator,
]
