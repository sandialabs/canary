# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import json
import os
from typing import Any

from ...workspace import Workspace
from ..hookspec import hookimpl
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
        cases = workspace.load_testcases()
        file = os.path.abspath(kwargs["output"] or self.default_output)
        data: dict = {}
        for case in cases:
            data[case.id] = case.asdict()
        with open(file, "w") as fh:
            json.dump(data, fh, indent=2)
