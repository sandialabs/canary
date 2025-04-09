# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from . import cdash
from . import gitlab
from . import html
from . import json
from . import junit
from . import markdown

plugins = [cdash, gitlab, html, json, junit, markdown]
