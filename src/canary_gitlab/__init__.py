# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import canary

from .reporter import GitLabMRReporter


@canary.hookimpl(specname="canary_session_reporter")
def gitlab_mr_reporter() -> canary.CanaryReporter:
    return GitLabMRReporter()
