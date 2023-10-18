import glob
import json
import os
from typing import TYPE_CHECKING

from ..session import Session
from ..test.partition import merge
from ..util import tty
from ..util.filesystem import mkdirp

if TYPE_CHECKING:
    from argparse import Namespace


description = "Merge batched test results"


def setup_parser(parser):
    parser.add_argument(
        "-o", default="merged.json", help="Output file name [default: %(default)s]"
    )
    parser.add_argument("files", nargs="+", help="Partitioned test files")


def merge_batches(args: "Namespace") -> int:
    files = args.files
    if len(files) == 1 and Session.is_workdir(files[0]):
        workdir = files[0]
        files = glob.glob(os.path.join(workdir, ".nvtest", "results.json.*"))
        if not files:
            tty.die(f"No files found in {workdir}")
    else:
        workdir = Session.find_workdir(files[0])
    merged = merge(files)
    mkdirp(os.path.dirname(args.o))
    cases = []
    for case in merged:
        cases.append(case.asdict())
    with open(args.o, "w") as fh:
        json.dump(cases, fh, indent=2)
    return 0
