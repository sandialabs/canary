# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import Any

import canary
from _canary.util.query_data import load_query_data

from .reporter import GitLabMRReporter


@canary.hookimpl(specname="canary_reporter")
def gitlab_mr_reporter() -> canary.CanaryReporter:
    return GitLabMRReporter()


@canary.hookimpl
def canary_capabilities() -> dict[str, Any] | None:
    return load_query_data("canary_gitlab.data", "capabilities.json")


@canary.hookimpl
def canary_skills() -> dict[str, Any] | None:
    return load_query_data("canary_gitlab.data", "skills.json")
