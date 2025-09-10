# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from . import batch_protocol
from . import discover
from . import email
from . import gitlab
from . import html
from . import json
from . import junit
from . import markdown
from . import mask
from . import partitioning
from . import post_clean
from . import pyt
from . import repeat
from . import reporting
from . import runtest_protocol
from . import runtests
from . import vvtest

plugins = [
    batch_protocol,
    discover,
    email,
    gitlab,
    html,
    json,
    junit,
    markdown,
    mask,
    partitioning,
    post_clean,
    pyt,
    repeat,
    reporting,
    runtest_protocol,
    runtests,
    vvtest,
]
