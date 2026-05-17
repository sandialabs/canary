# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
from typing import Any

from ...hookspec import hookimpl
from ...util import json_helper as json
from ...util.serialize import serialize
from ...workspace import Workspace
from ..types import CanaryReporter


@hookimpl
def canary_session_reporter() -> CanaryReporter:
    return JsonReporter()


class JsonReporter(CanaryReporter):
    type = "json"
    description = "JSON reporter"
    default_output = "canary.json"

    def create(self, **kwargs: Any) -> None:
        workspace = Workspace.load()
        jobs = workspace.load_jobs()
        file = os.path.abspath(kwargs["output"] or self.default_output)
        data: dict = {}
        for job in jobs:
            data[job.id] = serialize(job)
        with open(file, "w") as fh:
            json.dump(data, fh, indent=2)
