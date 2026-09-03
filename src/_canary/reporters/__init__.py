# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Canary reporter plugin registry.

Exposes all built-in report-format modules (html, json, junit, markdown) and
the base ``reporter`` module via the ``plugins`` list for plugin-manager discovery.
"""

from . import html
from . import json
from . import junit
from . import markdown
from . import reporter

plugins = [html, json, junit, markdown, reporter]
