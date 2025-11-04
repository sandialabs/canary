# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import json
import os
from typing import Any

from ...repo import Repo
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
        repo = Repo.load()
        cases = repo.load_testcases(latest=True)
        file = os.path.abspath(kwargs["output"] or self.default_output)
        data: dict = {}
        for case in cases:
            data[case.id] = case.getstate()
        with open(file, "w") as fh:
            json.dump(data, fh, indent=2)
