import json
import os

# from shlex import quote
from typing import TYPE_CHECKING

from ..test import Result

if TYPE_CHECKING:
    from ..test import TestCase


class JsonWriter:
    """Write test results to a json database."""

    def __init__(self, filename: str) -> None:
        self.filename = filename

    def prelude(self):
        #    "starttime": self.config.startdate.timestamp(),
        #    "startdate": self.config.startdate.strftime("%c"),
        #    "endtime": self.config.enddate.timestamp(),
        #    "enddate": self.config.enddate.strftime("%c"),
        #    "returncode": self.config.returncode,
        data = {
            "curdir": os.getcwd(),
            #    "command": " ".join(quote(_) for _ in config.get("invocation:args")),
            "compiler": None,
            #    "rundir": config.get("invocation:dir"),
            "starttime": None,
            "startdate": None,
            "endtime": None,
            "enddate": None,
            "returncode": None,
        }
        return data

    def dump(self, cases: list["TestCase"]) -> None:
        """
        This collects information from the given test list (a python list of
        TestExec objects), then writes a file in json format
        """
        data = self.prelude()
        if data["starttime"] > 0 and data["endtime"] > 0:
            data["duration"] = data["endtime"] - data["starttime"]
        else:
            data["duration"] = -1
        #    data["machine"] = config.get("machine")
        #    data["python"] = config.get("python")
        data["environment"] = strip_env(os.environ)
        counts = self.count_results(cases)
        data["tests"] = {
            "tests": len(cases),
            "pass": counts.get(Result.PASS, 0),
            "notdone": counts.get(Result.NOTDONE, 0),
            "notrun": counts.get(Result.NOTRUN, 0),
            "diff": counts.get(Result.DIFF, 0),
            "fail": counts.get(Result.FAIL, 0),
            "timeout": counts.get(Result.TIMEOUT, 0),
        }
        case_data = data["tests"].setdefault("cases", [])
        for case in cases:
            case_data.append(case.asdict())

        with open(self.filename, "w") as fh:
            json.dump({"nvtest": data}, fh, indent=2)

    def count_results(self, cases: list["TestCase"]):
        counts: dict[str, int] = {}
        for case in cases:
            counts[case.result.name] = counts.get(case.result.name, 0) + 1
        return counts


def strip_env(environ: os._Environ[str]) -> dict[str, str]:
    stripped = {}
    for (var, val) in environ.items():
        if var.startswith(("_", "BASH_FUNC_")):
            continue
        stripped[var] = val
    return stripped
