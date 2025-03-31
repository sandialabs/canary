#!/usr/bin/env python
# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import argparse


def add(a: int, b: int) -> int:
    return a + b


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("a", type=int)
    p.add_argument("b", type=int)
    args = p.parse_args()
    print(add(args.a, args.b))
