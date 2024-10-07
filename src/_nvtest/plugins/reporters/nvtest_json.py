import json
import os
from typing import Optional

from _nvtest.reporter import Reporter
from _nvtest.session import Session
from _nvtest.test.case import getstate as get_testcase_state


class JSONReporter(Reporter):

    def create(self, dest: Optional[str] = None) -> None:  # type: ignore
        """Collect information and create reports"""
        dest = dest or self.session.root
        file = os.path.join(dest, "Results.json")
        data: dict = {}
        for case in self.data.cases:
            data[case.id] = get_testcase_state(case)
        with open(file, "w") as fh:
            json.dump(data, fh, indent=2)
