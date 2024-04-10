import os
from typing import TYPE_CHECKING

from .. import config
from ..compat import vvtest
from ..test.testfile import AbstractTestFile
from ..util import logging

if TYPE_CHECKING:
    import argparse

    from _nvtest.config.argparsing import Parser


description = "Convert .vvt file to .pyt"


def setup_parser(parser: "Parser"):
    parser.add_argument("file", help="Test file")


def convert(args: "argparse.Namespace") -> int:
    if not args.file.endswith(".vvt"):
        raise ValueError("Can only convert .vvt to .pyt")
    file = AbstractTestFile(args.file)
    new_file = vvtest.to_pyt(file)
    f1 = os.path.relpath(file.file, config.invocation_dir)
    f2 = os.path.relpath(new_file, config.invocation_dir)
    logging.info(
        f"converted {f1} => {f2}\n"
        "NOTE: the conversion only converts the directives.\n"
        "The test body will need to be converted manually"
    )
    return 0
