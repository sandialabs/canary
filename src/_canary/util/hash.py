# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import hashlib


def hashit(string: str, length: int = 15) -> str:
    obj = hashlib.md5(string.encode("utf-8"))
    return obj.hexdigest()[:length]
