import json
import os

from _canary.reporter import Reporter


class JSONReporter(Reporter):
    def create(self, o: str = "./Results.json") -> None:  # type: ignore
        """Create JSON report

        Args:
          o: Output file name

        """
        file = os.path.abspath(o)
        data: dict = {}
        for case in self.data.cases:
            data[case.id] = case.getstate()
        with open(file, "w") as fh:
            json.dump(data, fh, indent=2)
