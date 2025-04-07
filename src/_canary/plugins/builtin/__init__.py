# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from . import email
from . import mask
from . import partitioning
from . import post_clean

plugins = [email, mask, post_clean, partitioning]
