# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""SHA-256 hashing utilities for canary."""

import hashlib


def hashit(string: str, length: int = 15) -> str:
    """Return the first ``length`` hex characters of the SHA-256 digest of ``string``.

    Args:
        string: Input string to hash.
        length: Number of hex characters to return (default 15).

    Returns:
        Truncated hexadecimal SHA-256 digest string.
    """
    obj = hashlib.sha256(string.encode("utf-8"))
    return obj.hexdigest()[:length]
