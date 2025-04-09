# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import json
import os
from typing import TYPE_CHECKING
from typing import Any

from ..hookspec import hookimpl
from ..types import CanaryReport

if TYPE_CHECKING:
    from ...session import Session


@hookimpl
def canary_session_report() -> CanaryReport:
    return JsonReport()


class JsonReport(CanaryReport):
    type = "json"
    description = "JSON reporter"

    def create(self, session: "Session | None" = None, **kwargs: Any) -> None:
        if session is None:
            raise ValueError("canary report html: session required")

        file = os.path.abspath(kwargs["output"] or "canary-report.json")
        data: dict = {}
        for case in session.cases:
            data[case.id] = case.getstate()
        with open(file, "w") as fh:
            json.dump(data, fh, indent=2)
