# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from . import archive
from . import capture
from . import cli
from . import email
from . import post_clean
from . import repeat
from . import testcase_generator

plugins = [archive, capture, cli, email, post_clean, repeat, testcase_generator]
