import json
import os

from _nvtest.reporter import Reporter
from _nvtest.session import Session
from _nvtest.test.case import getstate as get_testcase_state


class JSONReporter(Reporter):

    def create(self, o: str = "./Results.json") -> None:  # type: ignore
        """Create JSON report

        Args:
          o: Output file name

        """
        file = os.path.abspath(o)
        data: dict = {}
        for case in self.data.cases:
            data[case.id] = get_testcase_state(case)
        with open(file, "w") as fh:
            json.dump(data, fh, indent=2)
