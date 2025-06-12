# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from . import collectreport
from . import discover
from . import email
from . import mask
from . import partitioning
from . import post_clean
from . import runtests
from . import runtests_summary
from . import show_capture
from . import statusreport

plugins = [
    discover,
    email,
    mask,
    partitioning,
    post_clean,
    runtests,
    runtests_summary,
    collectreport,
    statusreport,
    show_capture,
]
