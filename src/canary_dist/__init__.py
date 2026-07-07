# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

try:
    from importlib.metadata import version

    __version__ = version("canary-distributed")
except Exception:
    __version__ = "unknown"
