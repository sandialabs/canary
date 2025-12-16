# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import os
from typing import Any
from typing import Generator

from ... import config
from ...generator import AbstractTestGenerator
from ...hookspec import hookimpl


@hookimpl(tryfirst=True, wrapper=True)
def canary_testcase_generator(
    root: str, path: str | None
) -> Generator[None, Any, AbstractTestGenerator | None]:
    res = yield
    if isinstance(res, type) and issubclass(res, AbstractTestGenerator):
        # old style hook returns a type, not the instance
        if res.matches(root if path is None else os.path.join(root, path)):
            return res(root, path=path)
    elif isinstance(res, AbstractTestGenerator):
        return res
    if generator := config.pluginmanager.hook.canary_generator(root=root, path=path):
        return generator
    return None
