# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from . import discover
from . import email
from . import mask
from . import partitioning
from . import post_clean
from . import show_capture

plugins = [discover, email, mask, partitioning, post_clean, show_capture]
