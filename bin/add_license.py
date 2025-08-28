#!/usr/bin/env python3

import argparse
import os


def add_python_license(file):
    license = """\
# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""
    with open(file) as fh:
        content = fh.read()
    if "# Copyright NTESS" in content:
        return
    with open(file, "w") as fh:
        if content.startswith("#!"):
            lines = content.splitlines(keepends=True)
            fh.write(lines[0])
            fh.write(license)
            fh.write("".join(lines[1:]))
        else:
            fh.write(license)
            fh.write(content)


def add_rst_license(file):
    license = """\
.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

"""
    with open(file) as fh:
        content = fh.read()
    if ".. Copyright NTESS" in content:
        return
    with open(file, "w") as fh:
        fh.write(license)
        fh.write(content)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("paths", nargs="+")
    args = p.parse_args()

    for path in args.paths:
        for dirname, dirs, files in os.walk(path):
            if dirname.endswith(("third_party", "TestResults")):
                del dirs[:]
                continue
            for file in files:
                if file.endswith((".py", ".pyt", ".vvt", ".cmake", ".sh")):
                    add_python_license(os.path.join(dirname, file))
                elif file.endswith(".rst"):
                    add_rst_license(os.path.join(dirname, file))
                    continue


if __name__ == "__main__":
    main()
