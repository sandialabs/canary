# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from . import batch_protocol
from . import discover
from . import email
from . import mask
from . import partitioning
from . import post_clean
from . import reporting
from . import runtest_protocol
from . import runtests

plugins = [
    batch_protocol,
    discover,
    email,
    mask,
    partitioning,
    post_clean,
    reporting,
    runtest_protocol,
    runtests,
]
